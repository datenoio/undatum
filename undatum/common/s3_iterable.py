"""S3 integration for iterable data processing."""

import logging
import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from iterable.helpers.detect import open_iterable

from ..common.command_utils import apply_iterable_csv_delimiter, apply_table_selection
from ..common.path_utils import (
    is_native_cloud_uri,
    is_s3_uri,
    looks_like_missing_cloud_dep,
    missing_cloud_extra_error,
)
from ..formats.s3 import get_s3_client, parse_s3_uri

logger = logging.getLogger(__name__)


def _configure_iterable(iterable: Any, path: str, iterableargs: dict) -> None:
    """Apply undatum-specific iterable configuration after open."""
    apply_iterable_csv_delimiter(iterable, path, iterableargs)


def _find_plugin_connector(path: str) -> Any:
    """Return a ConnectorPlugin that can handle the path, if any.

    Only consulted for URI-style paths (scheme://...) that are not s3://,
    so local file handling stays on the fast path.
    """
    if "://" not in path or is_s3_uri(path):
        return None
    try:
        from ..cli.plugins_cli import plugin_manager

        return plugin_manager.get_registry().find_connector(path)
    except Exception:
        return None


def _download_via_connector(connector: Any, path: str) -> str:
    """Download a connector-handled URI to a temp file and return its path."""
    suffix = os.path.splitext(path.split("?")[0])[1] or ".tmp"
    temp_fd, temp_file = tempfile.mkstemp(suffix=suffix)
    try:
        logger.info(f"Fetching {path} via connector plugin '{connector.name}'")
        with os.fdopen(temp_fd, "wb") as out, connector.open(path, mode="rb") as src:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                out.write(chunk)
    except Exception:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        raise
    return temp_file


@contextmanager
def open_iterable_with_s3(
    path: str,
    mode: str = "r",
    iterableargs: dict[str, Any] | None = None,
    region: str | None = None,
    profile: str | None = None,
) -> Iterator[Any]:
    """Open iterable data file, supporting local paths and cloud URIs.

    Supports local paths, ``s3://`` (via boto3, honoring ``region``/``profile``),
    and GCS/Azure/``s3a://`` URIs (delegated to iterabledata's native fsspec
    cloud support for both reading and writing).

    Args:
        path: File path or cloud URI (s3://, gs://, az://, abfs://, ...)
        mode: File mode ('r' for read, 'w' for write)
        iterableargs: Arguments for iterable processing
        region: AWS region (for s3:// URIs)
        profile: AWS profile name (for s3:// URIs)

    Yields:
        Iterable object (context manager)

    Raises:
        ImportError: If boto3 is not installed and an s3:// URI is provided
        ValueError: If S3 URI is invalid or credentials are missing
    """
    iterable = open_path(path, mode=mode, iterableargs=iterableargs, region=region, profile=profile)
    try:
        yield iterable
    finally:
        if hasattr(iterable, "close"):
            iterable.close()


def _s3fs_available() -> bool:
    """True when fsspec and s3fs are installed (streaming ``s3://`` reads)."""
    import importlib.util

    return (
        importlib.util.find_spec("fsspec") is not None
        and importlib.util.find_spec("s3fs") is not None
    )


def _codec_safe_source(path: str, iterableargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Keep the compression codec when ``--format-in`` is given for a compressed file.

    iterabledata 1.0.x drops the codec detected from the extension when an explicit
    format is passed, so ``data.csv.gz`` or ``data.zip`` read with ``format=csv`` would be
    parsed as raw bytes. For a compressed local file the explicit format is removed and,
    when the name does not already say it (``data.zip``), the file is opened through a
    temporary link named ``data.<format>.zip``.

    Returns:
        ``(path to open, reader options)``; the path differs from ``path`` only for a link,
        which the caller removes when the iterable is closed.
    """
    fmt = str(iterableargs.get("format") or "").lower()
    name = os.path.basename(path)
    if not fmt or "." not in name or not os.path.isfile(path):
        return path, iterableargs
    stem, codec = name.rsplit(".", 1)
    try:
        from iterable.helpers.open_iterable import _get_codec_registry

        codecs = set(_get_codec_registry())
    except Exception:  # pragma: no cover - private helper moved or renamed
        return path, iterableargs
    if codec.lower() not in codecs:
        return path, iterableargs
    args = {k: v for k, v in iterableargs.items() if k != "format"}
    if stem.lower().endswith(f".{fmt}"):
        return path, args
    fd, alias = tempfile.mkstemp(prefix="undatum-", suffix=f"-{stem}.{fmt}.{codec}")
    os.close(fd)
    os.remove(alias)
    try:
        os.symlink(os.path.abspath(path), alias)
    except OSError:  # no symlink support (e.g. Windows without privileges)
        shutil.copyfile(path, alias)
    return alias, args


class _TempFileCleanupIterable:
    """Wraps an iterable so close() also removes the backing temp file."""

    def __init__(self, inner: Any, temp_file: str) -> None:
        self._inner = inner
        self._temp_file = temp_file

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def __iter__(self) -> Iterator[Any]:
        return iter(self._inner)

    def close(self) -> None:
        try:
            self._inner.close()
        finally:
            if self._temp_file and os.path.exists(self._temp_file):
                try:
                    os.remove(self._temp_file)
                except OSError:
                    logger.warning(f"Failed to remove temporary file: {self._temp_file}")


def open_path(
    path: str,
    mode: str = "r",
    iterableargs: dict[str, Any] | None = None,
    region: str | None = None,
    profile: str | None = None,
    engine: str = "internal",
    codecargs: dict[str, Any] | None = None,
) -> Any:
    """Open a local path or cloud URI as an iterable (non-context-manager variant).

    Drop-in replacement for ``open_iterable`` that adds support for cloud URIs.
    GCS/Azure/``s3a://`` and S3 writes are delegated to iterabledata's native
    fsspec cloud support; ``s3://`` reads are downloaded to a temporary file
    (removed when ``close()`` is called) so AWS region/profile keep working.

    Args:
        path: File path or cloud URI (s3://, gs://, az://, abfs://, ...)
        mode: File mode ('r' for read, 'w' for write)
        iterableargs: Arguments for iterable processing
        region: AWS region (for S3 URIs)
        profile: AWS profile name (for S3 URIs)
        engine: iterabledata engine for file sources (default ``internal``)
        codecargs: Compression codec options (for example compression level)

    Returns:
        Iterable object with a ``close()`` method.
    """
    if iterableargs is None:
        iterableargs = {}
    extra: dict[str, Any] = {}
    if engine and engine != "internal":
        extra["engine"] = engine
    if codecargs:
        extra["codecargs"] = codecargs
    if mode in ("r", "rb"):
        iterableargs = apply_table_selection(path, iterableargs)

    # Database connection URIs are read via iterabledata's DB drivers.
    if mode in ("r", "rb"):
        from ..common.db_source import is_db_uri, open_db_source

        if is_db_uri(path):
            db_iterable = open_db_source(path, iterableargs=iterableargs)
            _configure_iterable(db_iterable, path, iterableargs)
            return db_iterable

    # GCS/Azure/s3a are opened directly by iterabledata (read and write).
    if is_native_cloud_uri(path):
        try:
            iterable = open_iterable(path, mode=mode, iterableargs=iterableargs, **extra)
        except Exception as exc:
            if looks_like_missing_cloud_dep(path, exc):
                raise missing_cloud_extra_error(path, exc) from exc
            raise
        _configure_iterable(iterable, path, iterableargs)
        return iterable

    if not is_s3_uri(path):
        connector = _find_plugin_connector(path)
        if connector is not None:
            if mode == "w":
                raise NotImplementedError(
                    "Write mode not supported for connector plugin URIs via iterable wrapper"
                )
            temp_file = _download_via_connector(connector, path)
            try:
                inner = open_iterable(temp_file, mode=mode, iterableargs=iterableargs, **extra)
            except Exception:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                raise
            _configure_iterable(inner, temp_file, iterableargs)
            return _TempFileCleanupIterable(inner, temp_file)
        if mode in ("r", "rb") and not iterableargs.get("delimiter"):
            # Same delimiter as the DuckDB reader (also for compressed CSV, which
            # iterabledata reads with "," otherwise).
            from .command_utils import resolve_csv_delimiter

            delimiter = resolve_csv_delimiter(
                iterableargs, filename=path, filetype=iterableargs.get("format")
            )
            if delimiter:
                iterableargs = {**iterableargs, "delimiter": delimiter}
        source, source_args = (
            _codec_safe_source(path, iterableargs) if mode in ("r", "rb") else (path, iterableargs)
        )
        if source != path:
            try:
                inner = open_iterable(source, mode=mode, iterableargs=source_args, **extra)
            except Exception:
                os.remove(source)
                raise
            _configure_iterable(inner, source, iterableargs)
            return _TempFileCleanupIterable(inner, source)
        iterableargs = source_args
        inner = open_iterable(path, mode=mode, iterableargs=iterableargs, **extra)
        _configure_iterable(inner, path, iterableargs)
        return inner

    if mode == "w":
        # Delegate S3 writes to iterabledata's native fsspec cloud support.
        return open_iterable(path, mode=mode, iterableargs=iterableargs, **extra)

    if _s3fs_available():
        # Stream the object through fsspec instead of downloading it first.
        storage_options = dict(iterableargs.get("storage_options") or {})
        if profile:
            storage_options.setdefault("profile", profile)
        if region:
            client_kwargs = dict(storage_options.get("client_kwargs") or {})
            client_kwargs.setdefault("region_name", region)
            storage_options["client_kwargs"] = client_kwargs
        args = {**iterableargs, "storage_options": storage_options}
        iterable = open_iterable(path, mode=mode, iterableargs=args, **extra)
        _configure_iterable(iterable, path, iterableargs)
        return iterable

    bucket, key = parse_s3_uri(path)
    client = get_s3_client(region=region, profile=profile)

    suffix = os.path.splitext(key)[1] or ".tmp"
    temp_fd, temp_file = tempfile.mkstemp(suffix=suffix)
    os.close(temp_fd)
    try:
        # Without s3fs (``pip install "undatum[cloud]"``) the object is downloaded first.
        logger.info(f"Downloading s3://{bucket}/{key} to temporary file")
        client.download_file(bucket, key, temp_file)
        inner = open_iterable(temp_file, mode=mode, iterableargs=iterableargs, **extra)
    except Exception:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        raise
    _configure_iterable(inner, temp_file, iterableargs)
    return _TempFileCleanupIterable(inner, temp_file)
