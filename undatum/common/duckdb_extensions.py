"""DuckDB extensions undatum uses, installed ahead of time for machines without network access.

Commands use an extension only when its file is already in the extension directory
(``UNDATUM_DUCKDB_EXTENSION_DIR`` or DuckDB's default); they never download one.
``undatum extensions install`` downloads them.
"""

from __future__ import annotations

import functools
import os
from typing import Any

from .duckdb_config import EXTENSION_DIR_ENV

# Name -> what undatum uses it for.
EXTENSIONS = {
    "encodings": "CSV text in encodings other than UTF-8 (Windows-1251, KOI8-R, Latin-1, ...)",
    "excel": "Excel workbooks",
    "httpfs": "HTTP(S) and S3 URLs",
    "spatial": "Geospatial formats and functions",
}
# Characters CSV parsing relies on; an encoding must write them as ASCII does.
_CSV_SYNTAX = '\r\n",;|\t'


def extension_directory(directory: str | None = None) -> str:
    """The extension directory: ``directory``, ``UNDATUM_DUCKDB_EXTENSION_DIR`` or DuckDB's
    default (``~/.duckdb/extensions``)."""
    chosen = directory or os.environ.get(EXTENSION_DIR_ENV)
    return os.path.abspath(os.path.expanduser(chosen or "~/.duckdb/extensions"))


@functools.cache
def _build() -> tuple[str, str]:
    """DuckDB's version and platform, which name the subdirectory of its extensions."""
    import duckdb

    conn = duckdb.connect()
    try:
        row = conn.execute("SELECT version(), (SELECT platform FROM pragma_platform())").fetchall()
    finally:
        conn.close()
    return str(row[0][0]), str(row[0][1])


def extension_path(name: str, directory: str | None = None) -> str:
    """Where the file of extension ``name`` is, or would be, installed."""
    version, platform = _build()
    return os.path.join(
        extension_directory(directory), version, platform, f"{name}.duckdb_extension"
    )


def extension_installed(name: str, directory: str | None = None) -> bool:
    """Whether extension ``name`` is installed (its file is present; nothing is downloaded)."""
    return os.path.isfile(extension_path(name, directory))


def extension_status(directory: str | None = None) -> list[dict[str, Any]]:
    """Name, purpose, installed, path and size (bytes) of every extension undatum uses."""
    rows = []
    for name, purpose in EXTENSIONS.items():
        path = extension_path(name, directory)
        installed = os.path.isfile(path)
        rows.append(
            {
                "name": name,
                "purpose": purpose,
                "installed": installed,
                "path": path,
                "size": os.path.getsize(path) if installed else None,
            }
        )
    return rows


def install_extensions(
    names: list[str], directory: str | None = None, *, force: bool = False
) -> list[dict[str, Any]]:
    """Download extensions ``names`` into the extension directory and check that they load.

    Args:
        names: Extension names (any DuckDB extension, usually from :data:`EXTENSIONS`).
        directory: Target directory; the configured one when omitted.
        force: Download again when the extension is already installed.

    Returns:
        One row per extension, as :func:`extension_status`, with ``downloaded``.

    Raises:
        ConfigurationError: An extension cannot be downloaded or does not load (exit code 2).
    """
    import duckdb

    from .errors import ConfigurationError

    target = extension_directory(directory)
    os.makedirs(target, exist_ok=True)
    conn = duckdb.connect(config={"extension_directory": target})
    rows = []
    try:
        for name in names:
            downloaded = force or not extension_installed(name, target)
            try:
                if downloaded:
                    conn.install_extension(name, force_install=force)
                conn.load_extension(name)
            except duckdb.Error as exc:
                raise ConfigurationError(
                    f"DuckDB extension '{name}' could not be installed in {target}: {exc}",
                    config_key=EXTENSION_DIR_ENV,
                    fix_hint="Check the network connection and the extension name.",
                ) from exc
            path = extension_path(name, target)
            rows.append(
                {
                    "name": name,
                    "purpose": EXTENSIONS.get(name, ""),
                    "installed": True,
                    "path": path,
                    "size": os.path.getsize(path) if os.path.isfile(path) else None,
                    "downloaded": downloaded,
                }
            )
    finally:
        conn.close()
    return rows


@functools.cache
def _encoding_names(directory: str) -> frozenset[str]:
    """Lower-case names of the encodings the installed ``encodings`` extension reads."""
    import duckdb

    conn = duckdb.connect(config={"extension_directory": directory})
    try:
        conn.load_extension("encodings")
        return frozenset(
            str(row[0]).lower()
            for row in conn.execute("SELECT name FROM duckdb_encodings()").fetchall()
        )
    except duckdb.Error:
        return frozenset()
    finally:
        conn.close()


def duckdb_encoding_name(encoding: str | None) -> str | None:
    """The name DuckDB reads text in ``encoding`` by, or ``None`` when it cannot.

    DuckDB needs the ``encodings`` extension installed, a name it knows, and an encoding that
    writes line endings, quotes and delimiters as ASCII does (not UTF-16 or UTF-32).
    """
    import codecs

    if not encoding or not extension_installed("encodings"):
        return None
    try:
        python_name = codecs.lookup(encoding).name
        if codecs.encode(_CSV_SYNTAX, python_name) != _CSV_SYNTAX.encode("ascii"):
            return None
    except (LookupError, UnicodeError):
        return None
    names = _encoding_names(extension_directory())
    for candidate in (encoding.lower(), python_name):
        if candidate in names:
            return candidate
    return None
