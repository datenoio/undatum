"""Results of informational commands, kept for unchanged files in ``~/.undatum/cache``.

``stats``, ``schema``, ``sniff``, ``analyze``, ``headers`` and ``count`` store their result for a
local file (:func:`cached`); a later run on the same file with the same options reads it instead
of the data. A result belongs to the file's real path, size and modification time (nanoseconds),
the undatum version and the options that change it, so a changed file gets new entries and
``undatum cache clear --stale`` removes the old ones (:func:`clear`). A file modified in the last
two seconds, or while it was read, is not cached.

Layout: ``<cache>/<file key>/source.json`` (path, size, mtime) and one
``<command>-<options key>.json`` per result. Entries are written atomically; one that cannot be
read or written is skipped without changing the command's result.

The CLI turns the cache on (:func:`cli_cache_option`); ``--no-cache``, ``UNDATUM_CACHE=0`` or
``defaults: cache: false`` in a config file turn it off. Library calls use it only with
``options["cache"]`` (or the environment/config) set.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

DIR_ENV = "UNDATUM_CACHE_DIR"
# Options that change how a result is shown or how fast it is computed, not the result itself.
PRESENTATION_OPTIONS = frozenset(
    {
        "cache",
        "output",
        "format_out",
        "output_format",
        "outtype",
        "format",
        "json",
        "json_output",
        "verbose",
        "quiet",
        "progress",
        "no_progress",
        "threads",
        "batch_size",
        "duckdb_threads",
        "duckdb_memory",
        "duckdb_temp_dir",
    }
)
SOURCE_FILE = "source.json"
# A file modified this recently may still change without a new mtime (coarse timestamps on some
# filesystems), so its result is not stored; like git's "racily clean" index entries.
RECENT_NS = 2_000_000_000


def cache_dir() -> Path:
    """The cache directory: ``UNDATUM_CACHE_DIR`` or ``~/.undatum/cache``."""
    override = os.environ.get(DIR_ENV)
    return Path(override).expanduser() if override else Path.home() / ".undatum" / "cache"


def cli_cache_option(flag: bool | None) -> bool:
    """Whether a CLI command uses the cache: the flag, else the environment/config, else on."""
    if flag is not None:
        return flag
    from .app_config import get_cli_defaults

    configured = get_cli_defaults().get("cache")
    return True if configured is None else bool(configured)


def cache_enabled(options: dict[str, Any]) -> bool:
    """Whether ``options`` (or the environment/config) turn the cache on."""
    from ..utils import get_option

    return bool(get_option(options, "cache"))


def _source(path: str) -> dict[str, Any] | None:
    """Identity of a local regular file, or ``None`` for stdin, URIs and other paths."""
    if not isinstance(path, str) or path in ("", "-") or "://" in path:
        return None
    try:
        real = os.path.realpath(path)
        info = os.stat(real)
    except OSError:
        return None
    if not os.path.isfile(real):
        return None
    return {"path": real, "size": info.st_size, "mtime_ns": info.st_mtime_ns}


def _digest(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _file_key(source: dict[str, Any]) -> str:
    return _digest([source["path"], source["size"], source["mtime_ns"]])[:32]


def _options_key(command: str, options: dict[str, Any], path: str) -> str:
    """Key of the command, version, options and the path as given (results may show it)."""
    from .. import __version__

    relevant = {
        key: value
        for key, value in options.items()
        if key not in PRESENTATION_OPTIONS and value is not None and not key.startswith("_")
    }
    return _digest({"command": command, "version": __version__, "path": path, "options": relevant})[
        :16
    ]


def _write_json(path: Path, document: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf8") as handle:
            json.dump(document, handle, ensure_ascii=False, default=str)
        os.replace(temp, path)
    except BaseException:
        if os.path.exists(temp):
            os.remove(temp)
        raise


def cached(
    command: str,
    path: str,
    options: dict[str, Any],
    compute: Callable[[], T],
    load: Callable[[Any], T] | None = None,
    dump: Callable[[T], Any] | None = None,
) -> T:
    """The result of ``compute()`` for ``path``, read from the cache when the file is unchanged.

    Args:
        command: Command name (part of the key).
        path: Input file; only local regular files are cached.
        options: Command options; ``cache`` turns the cache on, the others are part of the key
            (except :data:`PRESENTATION_OPTIONS`).
        compute: Computes the result.
        load: Turns a stored JSON value back into the result (default: as is).
        dump: Turns the result into a JSON value (default: ``normalize_for_json``).

    Returns:
        The result, computed or read from the cache.
    """
    if not cache_enabled(options):
        return compute()
    source = _source(path)
    if source is None:
        return compute()
    folder = cache_dir() / _file_key(source)
    entry = folder / f"{command}-{_options_key(command, options, path)}.json"
    try:
        with open(entry, encoding="utf8") as handle:
            stored = json.load(handle)
        result = load(stored["result"]) if load else stored["result"]
        logger.info("%s: using the cached result for %s (%s)", command, path, entry)
        return result
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.debug("%s: ignoring the cache entry %s: %s", command, entry, exc)

    result = compute()
    if _source(path) != source:
        logger.debug("%s: %s changed while it was read; not cached", command, path)
        return result
    if time.time_ns() - source["mtime_ns"] < RECENT_NS:
        logger.debug("%s: %s was modified in the last 2 seconds; not cached", command, path)
        return result
    try:
        from ..utils import normalize_for_json

        value = dump(result) if dump else result
        if not (folder / SOURCE_FILE).exists():
            _write_json(folder / SOURCE_FILE, source)
        _write_json(
            entry,
            {
                "command": command,
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "result": normalize_for_json(value),
            },
        )
    except (OSError, TypeError, ValueError) as exc:
        logger.debug("%s: could not cache the result for %s: %s", command, path, exc)
    return result


def _folder_size(folder: Path) -> int:
    return sum(item.stat().st_size for item in folder.iterdir() if item.is_file())


def entries() -> list[dict[str, Any]]:
    """The cached files: path, size, mtime, stale, bytes and their results.

    ``stale`` is true when the file is gone or its size or modification time changed.
    """
    root = cache_dir()
    if not root.is_dir():
        return []
    listed = []
    for folder in sorted(root.iterdir()):
        source_file = folder / SOURCE_FILE
        if not folder.is_dir() or not source_file.is_file():
            continue
        try:
            source = json.loads(source_file.read_text(encoding="utf8"))
        except (OSError, ValueError):
            continue
        results = []
        for item in sorted(folder.glob("*.json")):
            if item.name == SOURCE_FILE:
                continue
            try:
                stored = json.loads(item.read_text(encoding="utf8"))
            except (OSError, ValueError):
                continue
            results.append(
                {
                    "command": stored.get("command"),
                    "created": stored.get("created"),
                    "bytes": item.stat().st_size,
                }
            )
        current = _source(source.get("path", ""))
        listed.append(
            {
                "path": source.get("path"),
                "size": source.get("size"),
                "mtime": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(source.get("mtime_ns", 0)) / 1e9)
                ),
                "stale": current is None or _file_key(current) != folder.name,
                "bytes": _folder_size(folder),
                "results": results,
                "_folder": folder,
            }
        )
    return listed


def clear(stale_only: bool = False) -> tuple[int, int]:
    """Remove cached entries (all, or those of missing and changed files).

    Returns:
        Number of files whose entries were removed, and the bytes freed.
    """
    removed = freed = 0
    if stale_only:
        folders = [(entry["_folder"], entry["bytes"]) for entry in entries() if entry["stale"]]
    else:
        root = cache_dir()
        folders = [
            (folder, _folder_size(folder))
            for folder in (sorted(root.iterdir()) if root.is_dir() else [])
            if folder.is_dir()
        ]
    for folder, size in folders:
        shutil.rmtree(folder, ignore_errors=True)
        removed += 1
        freed += size
    return removed, freed
