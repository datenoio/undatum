"""Record writers for command output files.

Commands that produce records write them through :class:`RecordSink` (streaming)
or :func:`write_records` (one call). Both delegate to iterabledata's
``open_iterable(..., mode="w")`` so every writable format and compression by
extension works. Local files are written to a temporary sibling and renamed on
success, so a failed command never leaves an empty or partial output file.
"""

from __future__ import annotations

import itertools
import logging
import os
import tempfile
from collections.abc import Iterable
from typing import Any

from .errors import FormatError
from .format_names import FAST_WRITABLE, format_from_name
from .path_utils import is_uri

logger = logging.getLogger(__name__)

# Extensions that iterabledata detects as CSV but that must use a tab delimiter.
TAB_DELIMITED_EXTENSIONS = {"tsv", "tab"}

# Compression extensions recognised without importing codec modules.
CODEC_EXTENSIONS = {"gz", "gzip", "zst", "zstd", "bz2", "xz", "lz4", "7z", "zip", "br", "lzo", "sz"}

# Shown in "cannot be written" errors; the full list is in ``undatum formats list --writable``.
COMMON_WRITABLE_FORMATS = ["avro", "bson", "csv", "json", "jsonl", "parquet", "tsv", "yaml"]

TEMP_PREFIX = ".undatum-tmp-"


def split_codec_suffix(path: str) -> tuple[str, str | None]:
    """Split a compression suffix off ``path``: ``a.csv.gz`` -> (``a.csv``, ``gz``)."""
    name = os.path.basename(path)
    if "." in name:
        base, ext = path.rsplit(".", 1)
        if ext.lower() in CODEC_EXTENSIONS and "." in os.path.basename(base):
            return base, ext.lower()
    return path, None


def _extension(path: str) -> str:
    base, _ = split_codec_suffix(path)
    name = os.path.basename(base)
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _detect(path: str) -> Any:
    """Run iterabledata detection, turning missing codec dependencies into DependencyError."""
    from iterable.helpers.detect import detect_file_type

    try:
        return detect_file_type(path)
    except ImportError as exc:
        from .errors import DependencyError

        raise DependencyError(
            "iterabledata[compression]",
            feature=f"writing '{os.path.basename(path)}'",
            install_command='pip install "iterabledata[compression]"',
        ) from exc


def resolve_output_format(path: str, format_out: str | None = None) -> str:
    """Return the iterabledata format id for an output path.

    Args:
        path: Output file path or cloud URI.
        format_out: Explicit format id that overrides detection by extension.

    Returns:
        The format id (for example ``csv``, ``parquet``).

    Raises:
        FormatError: If the format is unknown or cannot be written.
    """
    if format_out:
        format_id = format_out.lower()
    else:
        fast = format_from_name(path)
        format_id = fast[0] if fast else ""
    # Common formats need no capability check (which imports iterabledata).
    if format_id in FAST_WRITABLE:
        return format_id

    from iterable.helpers.capabilities import supports_write

    if not format_id:
        detected = _detect(path)
        if not detected.get("success") or detected.get("datatype") is None:
            name = os.path.basename(path)
            ext = name.rsplit(".", 1)[-1] if "." in name else name
            raise FormatError(path, ext, COMMON_WRITABLE_FORMATS, output=True)
        format_id = detected["datatype"].id()

    try:
        writable = supports_write(format_id)
    except Exception:
        writable = False
    if not writable:
        raise FormatError(path, format_id, COMMON_WRITABLE_FORMATS, output=True)
    return format_id


def _is_flat_only(format_id: str) -> bool:
    """Return True when the format needs a fixed column list (CSV, TSV, ...)."""
    if format_id in ("csv", "tsv"):
        return True
    try:
        from iterable.helpers.capabilities import get_format_capabilities

        return bool(get_format_capabilities(format_id).get("flat_only"))
    except Exception:
        return False


def collect_fieldnames(records: Iterable[dict[str, Any]]) -> list[str]:
    """Return the union of record keys in first-seen order."""
    seen: dict[str, None] = {}
    for record in records:
        if isinstance(record, dict):
            for key in record:
                seen.setdefault(key, None)
    return list(seen)


def _open_writer(target: str, format_id: str, args: dict[str, Any]) -> Any:
    """Open an iterabledata writer for ``target``.

    ``open_iterable`` passes options through ``options=``, but ``CSVIterable`` reads the
    delimiter and quote character only from constructor arguments, so CSV output with a
    non-default delimiter (TSV) is constructed directly.
    """
    from iterable.helpers.detect import open_iterable

    delimiter = args.get("delimiter")
    quotechar = args.get("quotechar")
    if format_id == "csv" and (delimiter not in (None, ",") or quotechar not in (None, '"')):
        from iterable.datatypes.csv import CSVIterable

        kwargs: dict[str, Any] = {
            "keys": args.get("keys"),
            "delimiter": delimiter or ",",
            "quotechar": quotechar or '"',
            "mode": "w",
            "encoding": args.get("encoding"),
        }
        codec_cls = _detect(target).get("codec")
        if codec_cls is not None:
            return CSVIterable(codec=codec_cls(filename=target, mode="w"), **kwargs)
        return CSVIterable(filename=target, **kwargs)
    return open_iterable(target, mode="w", iterableargs=args)


def _temp_sibling(path: str) -> str:
    directory = os.path.dirname(os.path.abspath(path))
    fd, target = tempfile.mkstemp(
        prefix=TEMP_PREFIX, suffix="-" + os.path.basename(path), dir=directory
    )
    os.close(fd)
    os.remove(target)
    return target


_ARROW_FORMATS = ("parquet", "orc", "feather")


def _write_empty_arrow(path: str, format_id: str, fieldnames: list[str]) -> None:
    """Write a valid columnar file with no rows (string columns ``fieldnames``)."""
    import pyarrow as pa

    table = pa.table({name: pa.array([], type=pa.string()) for name in fieldnames})
    if format_id == "parquet":
        import pyarrow.parquet as pq

        pq.write_table(table, path)
    elif format_id == "orc":
        from pyarrow import orc

        orc.write_table(table, path)
    else:
        from pyarrow import feather

        feather.write_feather(table, path)


class RecordSink:
    """Streaming, atomic record writer for one output file.

    The writer opens lazily on the first batch, so flat formats can take their header
    from the first records when ``fieldnames`` is not given. Use it as a context
    manager: the file is published on normal exit and discarded on an exception.

    Example:
        >>> with RecordSink("out.parquet") as sink:
        ...     sink.write_batch([{"a": 1}, {"a": 2}])
    """

    def __init__(
        self,
        path: str,
        fieldnames: list[str] | None = None,
        format_out: str | None = None,
        iterableargs: dict[str, Any] | None = None,
    ):
        self.path = path
        self.format_id = resolve_output_format(path, format_out)
        self.fieldnames = list(fieldnames) if fieldnames else None
        self.format_out = format_out
        self.iterableargs = iterableargs or {}
        self.count = 0
        self._atomic = not is_uri(path)
        self._target = _temp_sibling(path) if self._atomic else path
        self._writer: Any = None

    def _args(self) -> dict[str, Any]:
        args: dict[str, Any] = {}
        if self.fieldnames:
            args["keys"] = list(self.fieldnames)
        if self.format_id == "csv" and _extension(self.path) in TAB_DELIMITED_EXTENSIONS:
            args["delimiter"] = "\t"
        if self.format_out:
            args["format"] = self.format_id
        args.update({k: v for k, v in self.iterableargs.items() if v is not None})
        return args

    def write_batch(self, records: list[dict[str, Any]]) -> None:
        """Write a batch of records."""
        from ..utils import normalize_for_json

        if not records:
            return
        if self._writer is None:
            if self.fieldnames is None and _is_flat_only(self.format_id):
                self.fieldnames = collect_fieldnames(records)
            self._writer = _open_writer(self._target, self.format_id, self._args())
        self._writer.write_bulk([normalize_for_json(record) for record in records])
        self.count += len(records)

    def close(self) -> None:
        """Finish writing and publish the file (an empty input still yields a file)."""
        if self._writer is None and self.format_id in _ARROW_FORMATS and self._atomic:
            # A columnar file needs a schema; the iterabledata writer would leave 0 bytes.
            _write_empty_arrow(self._target, self.format_id, self.fieldnames or [])
            os.replace(self._target, self.path)
            return
        if self._writer is None:
            self._writer = _open_writer(self._target, self.format_id, self._args())
        self._writer.close()
        self._writer = None
        if self._atomic:
            os.replace(self._target, self.path)

    def abort(self) -> None:
        """Discard the output after a failure."""
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:  # pragma: no cover - best effort cleanup
                logger.debug("Failed to close writer for %s", self._target, exc_info=True)
            self._writer = None
        if self._atomic and os.path.exists(self._target):
            os.remove(self._target)

    def __enter__(self) -> RecordSink:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, *exc: object) -> None:
        if exc_type is None:
            self.close()
        else:
            self.abort()


def write_records(
    path: str,
    records: Iterable[dict[str, Any]],
    fieldnames: list[str] | None = None,
    format_out: str | None = None,
    iterableargs: dict[str, Any] | None = None,
    batch_size: int = 1000,
) -> int:
    """Write records to ``path`` in the format implied by its extension.

    Args:
        path: Output file path or cloud URI.
        records: Records to write (a list or any iterable).
        fieldnames: Column order for flat formats. When omitted, a list input uses the
            union of its keys and a streaming input uses the first batch's keys.
        format_out: Explicit output format id.
        iterableargs: Extra writer options passed to iterabledata.
        batch_size: Number of records per ``write_bulk`` call.

    Returns:
        Number of records written.

    Raises:
        FormatError: If the output format cannot be written.
    """
    if fieldnames is None and isinstance(records, (list, tuple)):
        fieldnames = collect_fieldnames(records)
    with RecordSink(path, fieldnames, format_out, iterableargs) as sink:
        iterator = iter(records)
        while True:
            batch = list(itertools.islice(iterator, batch_size))
            if not batch:
                break
            sink.write_batch(batch)
    return sink.count


class StdoutSink:
    """Incremental record writer for standard output.

    Text formats (``csv``, ``tsv``, ``jsonl``, ``json``) are written as batches arrive:
    the CSV/TSV header once, a JSON array opened on the first batch and closed by
    :meth:`close`. Binary formats (Parquet, ...) are refused when stdout is a terminal
    and otherwise collected in a temporary file that :meth:`close` copies to stdout.

    Args:
        fmt: Output format.
        fieldnames: CSV/TSV header; defaults to the first record's keys.
    """

    TEXT_FORMATS = ("csv", "tsv", "jsonl", "json")

    def __init__(self, fmt: str = "jsonl", fieldnames: list[str] | None = None):
        import sys

        fmt = (fmt or "jsonl").lower()
        self.fmt = "jsonl" if fmt == "ndjson" else fmt
        self.fieldnames = fieldnames
        self.count = 0
        self._stream = sys.stdout
        self._csv: Any = None
        self._binary: RecordSink | None = None
        self._tmp_path: str | None = None
        if self.fmt not in self.TEXT_FORMATS:
            if hasattr(self._stream, "isatty") and self._stream.isatty():
                from .errors import ValidationError

                raise ValidationError(
                    f"Refusing to write binary '{self.fmt}' data to a terminal; "
                    "use --output or redirect stdout",
                    field="format_out",
                )
            tmp_fd, self._tmp_path = tempfile.mkstemp(suffix=f".{self.fmt}")
            os.close(tmp_fd)
            os.remove(self._tmp_path)
            self._binary = RecordSink(self._tmp_path, fieldnames, self.fmt)

    def write_batch(self, records: Iterable[dict[str, Any]]) -> None:
        """Write a batch of records."""
        import csv
        import json

        from ..utils import normalize_for_json

        if self._binary is not None:
            batch = list(records)
            self._binary.write_batch(batch)
            self.count += len(batch)
            return
        stream = self._stream
        for record in records:
            record = normalize_for_json(record)
            if self.fmt in ("csv", "tsv"):
                if self._csv is None:
                    self._csv = csv.DictWriter(
                        stream,
                        fieldnames=self.fieldnames or list(record.keys()),
                        delimiter="\t" if self.fmt == "tsv" else ",",
                        extrasaction="ignore",
                        lineterminator="\n",
                    )
                    self._csv.writeheader()
                self._csv.writerow(record)
            elif self.fmt == "jsonl":
                stream.write(json.dumps(record, ensure_ascii=False, default=str))
                stream.write("\n")
            else:
                stream.write(",\n" if self.count else "[\n")
                stream.write(json.dumps(record, ensure_ascii=False, default=str))
            self.count += 1

    def close(self) -> int:
        """Finish the output and return the number of records written."""
        import shutil

        if self._binary is not None:
            try:
                self._binary.close()
                self._stream.flush()
                with open(self._tmp_path, "rb") as handle:  # type: ignore[arg-type]
                    shutil.copyfileobj(handle, self._stream.buffer)
                self._stream.buffer.flush()
            finally:
                self._binary = None
                if self._tmp_path and os.path.exists(self._tmp_path):
                    os.remove(self._tmp_path)
        elif self.fmt == "json":
            self._stream.write("\n]\n" if self.count else "[]\n")
        return self.count


def write_stdout(
    records: Iterable[dict[str, Any]],
    fmt: str = "jsonl",
    fieldnames: list[str] | None = None,
) -> int:
    """Stream records to standard output (see :class:`StdoutSink`).

    Args:
        records: Records to write.
        fmt: Output format.
        fieldnames: CSV/TSV header; defaults to the first record's keys.

    Returns:
        Number of records written.
    """
    sink = StdoutSink(fmt, fieldnames)
    iterator = iter(records)
    while True:
        batch = list(itertools.islice(iterator, 1000))
        if not batch:
            break
        sink.write_batch(batch)
    return sink.close()


def emit_records(
    records: Iterable[dict[str, Any]],
    to_file: str | None = None,
    fieldnames: list[str] | None = None,
    format_out: str | None = None,
    stdout_format: str | None = None,
) -> int:
    """Write command results to ``to_file`` or, when it is empty, to stdout.

    On stdout the format is, in order: ``stdout_format``, ``format_out``, the format the
    CLI derived from ``--format-out`` or the input file (see :mod:`undatum.common.stdio`),
    and finally JSON Lines.

    Args:
        records: Records produced by a command.
        to_file: Output path; stdout is used when ``None`` or empty.
        fieldnames: Column order for flat formats.
        format_out: Explicit output format id.
        stdout_format: Format forced by the command for stdout.

    Returns:
        Number of records written.
    """
    from .stdio import format_out_override
    from .stdio import stdout_format as stdout_format_hint

    if to_file:
        return write_records(
            to_file,
            records,
            fieldnames=fieldnames,
            format_out=format_out or format_out_override.get(),
        )

    fmt = stdout_format or format_out or stdout_format_hint.get() or "jsonl"
    return write_stdout(records, fmt, fieldnames=fieldnames)


# DuckDB COPY options per output extension (after stripping the compression suffix).
_DUCKDB_COPY_FORMATS = {
    "csv": "FORMAT CSV, HEADER",
    "tsv": "FORMAT CSV, HEADER, DELIMITER '\t'",
    "tab": "FORMAT CSV, HEADER, DELIMITER '\t'",
    "jsonl": "FORMAT JSON",
    "ndjson": "FORMAT JSON",
    "json": "FORMAT JSON, ARRAY true",
    "parquet": "FORMAT PARQUET",
}
_DUCKDB_COPY_CODECS = {None: None, "gz": "gzip", "gzip": "gzip", "zst": "zstd", "zstd": "zstd"}


def duckdb_copy_options(path: str) -> str | None:
    """Return the DuckDB ``COPY`` option string for ``path`` or ``None`` if unsupported."""
    if is_uri(path):
        return None
    _, codec_id = split_codec_suffix(path)
    if codec_id not in _DUCKDB_COPY_CODECS:
        return None
    options = _DUCKDB_COPY_FORMATS.get(_extension(path))
    if options is None:
        return None
    compression = _DUCKDB_COPY_CODECS[codec_id]
    if compression:
        if _extension(path) == "parquet":
            return None
        options += f", COMPRESSION {compression}"
    return options


def duckdb_copy_to_file(conn: Any, query: str, path: str) -> bool:
    """Write ``query`` results to ``path`` with DuckDB ``COPY`` when the format allows.

    The result is written to a temporary sibling and renamed on success.

    Args:
        conn: Open DuckDB connection.
        query: SELECT query whose rows are written.
        path: Output path.

    Returns:
        True if the file was written, False if DuckDB cannot write this format natively
        (the caller should fetch rows and use :func:`write_records`).
    """
    options = duckdb_copy_options(path)
    if options is None:
        return False
    target = _temp_sibling(path)
    escaped = target.replace("'", "''")
    try:
        conn.execute(f"COPY ({query}) TO '{escaped}' ({options})")
        os.replace(target, path)
    except BaseException:
        if os.path.exists(target):
            os.remove(target)
        raise
    return True
