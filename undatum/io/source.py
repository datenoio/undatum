"""Record sources: one way to read rows from files, stdin spools, cloud URIs and databases."""

from __future__ import annotations

import itertools
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from ..common.command_utils import (
    duckdb_read_expr,
    get_iterable_options,
    iter_command_rows,
)
from ..common.format_names import format_from_name

logger = logging.getLogger(__name__)

# Reader options that DuckDB's native readers cannot honour; with any of them set the
# rows are read through iterabledata.
_PYTHON_ONLY_OPTIONS = ("table", "sheet", "flatten_nested", "tagname", "start_line", "trust")
# Formats DuckDB does not read but pyarrow does (``pyarrow.dataset`` is not used: it imports
# pandas, about 2 s).
_ARROW_FORMATS = ("orc", "arrow")
# Names of the Arrow readers registered on DuckDB connections.
_arrow_names = itertools.count()


@dataclass
class RowSource:
    """Rows of one input, read lazily.

    Args:
        path: File path, ``-`` spool, cloud URI or database URI.
        options: Command options; reader options (``format_in``, ``delimiter``,
            ``encoding``, ``table``, ``flatten_nested``, ``on_error``, ...) are taken from it.
    """

    path: str
    options: dict[str, Any] = field(default_factory=dict)

    def __iter__(self) -> Iterator[Any]:
        from ..common.s3_iterable import open_path

        iterable = open_path(self.path, mode="r", iterableargs=get_iterable_options(self.options))
        try:
            yield from iter_command_rows(iterable, self.options)
        finally:
            iterable.close()

    @property
    def format_id(self) -> str | None:
        """Input format: ``--format-in`` or the format detected from the file."""
        explicit = self.options.get("format_in") or self.options.get("filetype")
        if explicit:
            return str(explicit).lower()
        return self._detected()[0]

    def _detected(self) -> tuple[str | None, str | None]:
        # Common extensions are recognised without importing iterabledata (about 1 s).
        fast = format_from_name(self.path)
        if fast is not None:
            return fast
        from iterable.helpers.detect import detect_file_type

        try:
            result: Any = detect_file_type(self.path)
        except Exception:  # noqa: BLE001 - detection is best effort
            return None, None
        if not result.get("success") or result.get("datatype") is None:
            return None, None
        codec = result["codec"].id() if result.get("codec") is not None else None
        return result["datatype"].id(), codec

    def _python_only(self) -> bool:
        """Whether only the Python reader can read this source: not a local file, or options
        no other reader applies (a named sheet or table, nested flattening,
        ``--on-error skip|warn``, XML tags)."""
        if "://" in self.path or not os.path.isfile(self.path):
            return True
        if any(self.options.get(key) for key in _PYTHON_ONLY_OPTIONS):
            return True
        return self.options.get("on_error") in ("skip", "warn")

    def duckdb_from(self) -> str | None:
        """Return a DuckDB ``FROM`` expression for this source, or ``None``.

        DuckDB reads CSV, TSV, JSON, JSON Lines and Parquet (optionally gzip/zstd
        compressed) natively. Options it cannot apply — a named sheet or table, nested
        flattening, ``--on-error skip|warn``, XML tags — CSV text in an encoding DuckDB does
        not read (anything but UTF-8 without the ``encodings`` extension), and CSV headers
        DuckDB cannot name as the Python reader does (empty, or names that differ only by
        case) force the Python reader. CSV is read as text with the header the Python reader
        takes from the first line.
        """
        from ..constants import DUCKABLE_CODECS, DUCKABLE_FILE_TYPES

        if self._python_only():
            return None
        detected_format, codec = self._detected()
        fmt = self.format_id or detected_format
        if fmt not in (*DUCKABLE_FILE_TYPES, "tsv") or (codec or "raw") not in DUCKABLE_CODECS:
            return None
        if fmt == "tsv":
            fmt = "csv"
        try:
            # CSV is read as text, like the Python reader, so both engines agree.
            return duckdb_read_expr(
                self.path, fmt, get_iterable_options(self.options), all_varchar=True
            )
        except ValueError:
            return None

    def arrow_reader(self, columns: list[str] | None = None) -> Any | None:
        """A new ``pyarrow.RecordBatchReader`` over the input, or ``None``.

        For formats DuckDB does not read but pyarrow does: ORC (stripe by stripe) and Arrow
        IPC/Feather v2 files or streams (memory-mapped). ``None`` for other formats,
        compressed or remote files, options only the Python reader applies, and files pyarrow
        cannot open (Feather v1, ORC without pyarrow ORC support).

        Args:
            columns: Read only these top-level columns (DuckDB cannot select the columns of
                a reader itself); ``None`` reads all.
        """
        if self._python_only():
            return None
        detected_format, codec = self._detected()
        fmt = self.format_id or detected_format
        if fmt not in _ARROW_FORMATS or codec not in (None, "raw"):
            return None
        try:
            import pyarrow as pa

            if fmt == "orc":
                from pyarrow import orc

                orc_file = orc.ORCFile(self.path)
                if columns is None:
                    stripes = (orc_file.read_stripe(i) for i in range(orc_file.nstripes))
                    return pa.RecordBatchReader.from_batches(orc_file.schema, stripes)
                schema = pa.schema([orc_file.schema.field(name) for name in columns])
                # read_stripe() keeps the file's column order; the schema has the requested one
                # (a reader whose batches do not match its schema crashes DuckDB).
                stripes = (
                    orc_file.read_stripe(i, columns=columns).select(columns)
                    for i in range(orc_file.nstripes)
                )
                return pa.RecordBatchReader.from_batches(schema, stripes)
            source = pa.memory_map(self.path)
            try:
                ipc: Any = pa.ipc.open_file(source)
                batches = (ipc.get_batch(i) for i in range(ipc.num_record_batches))
            except pa.ArrowInvalid:
                source.seek(0)
                ipc = pa.ipc.open_stream(source)
                batches = iter(ipc)
            if columns is None:
                return pa.RecordBatchReader.from_batches(ipc.schema, batches)
            schema = pa.schema([ipc.schema.field(name) for name in columns])
            return pa.RecordBatchReader.from_batches(
                schema, (batch.select(columns) for batch in batches)
            )
        except Exception as exc:  # noqa: BLE001 - any failure leaves the Python reader
            logger.debug("%s: not readable with pyarrow: %s", self.path, exc)
            return None

    def csv_header(self) -> list[str] | None:
        """Field names the Python reader takes from the first line of a CSV or TSV file.

        ``None`` when the source is not a local CSV/TSV file or its first line cannot be
        read (a codec without its module, text that does not decode).
        """
        from ..common.command_utils import read_csv_header, resolve_csv_delimiter

        if self._python_only():
            return None
        detected_format, codec = self._detected()
        fmt = self.format_id or detected_format
        if fmt not in ("csv", "tsv"):
            return None
        iterableargs = get_iterable_options(self.options)
        delimiter = resolve_csv_delimiter(iterableargs, filename=self.path, filetype=fmt) or ","
        return read_csv_header(
            self.path,
            delimiter,
            encoding=iterableargs.get("encoding"),
            quotechar=iterableargs.get("quotechar"),
            codec=codec,
        )

    def duckdb_readable(self) -> bool:
        """Whether DuckDB reads this source, natively or through :meth:`arrow_reader`."""
        if self.duckdb_from() is not None:
            return True
        if self._python_only():
            return False
        detected_format, codec = self._detected()
        if (self.format_id or detected_format) not in _ARROW_FORMATS:
            return False
        return self.arrow_reader() is not None

    def duckdb_relation(self, conn: Any, columns: list[str] | None = None) -> str | None:
        """A DuckDB ``FROM`` expression for this source on ``conn``, or ``None``.

        The native reader (:meth:`duckdb_from`) when DuckDB reads the format, else a new
        :meth:`arrow_reader` registered on ``conn``. DuckDB reads a registered reader once:
        such a relation serves one query (``DESCRIBE`` does not read it), and a query that
        reads it again fails with a DuckDB error, which the callers answer with the Python
        engine.

        Args:
            conn: DuckDB connection.
            columns: The only columns the query uses (top-level names), so that an Arrow
                reader reads only them; ``None`` for all.
        """
        relation = self.duckdb_from()
        if relation is not None:
            return relation
        reader = self.arrow_reader(columns)
        if reader is None:
            return None
        name = f"undatum_arrow_{next(_arrow_names)}"
        conn.register(name, reader)
        return name


def side_options(options: dict[str, Any] | None, side: int) -> dict[str, Any]:
    """Options for one input of a two-input command.

    The second input uses ``table2`` / ``sheet2`` / ``start_page2`` instead of the first
    input's table selection; everything else is shared.
    """
    options = dict(options or {})
    if side == 2:
        options["table"] = options.get("table2")
        options["sheet"] = options.get("sheet2")
        options["start_page"] = options.get("start_page2")
    return options


def open_source(path: str, options: dict[str, Any] | None = None) -> RowSource:
    """Return a lazy :class:`RowSource` for ``path``.

    Args:
        path: Input path or URI (``-`` has already been spooled by the CLI).
        options: Command options with reader settings.

    Returns:
        The source; iterate it for rows.
    """
    return RowSource(path, dict(options or {}))
