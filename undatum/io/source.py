"""Record sources: one way to read rows from files, stdin spools, cloud URIs and databases."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from ..common.command_utils import duckdb_read_expr, get_iterable_options, iter_command_rows
from ..common.format_names import format_from_name

logger = logging.getLogger(__name__)

# Reader options that DuckDB's native readers cannot honour; with any of them set the
# rows are read through iterabledata.
_PYTHON_ONLY_OPTIONS = ("table", "sheet", "flatten_nested", "tagname", "start_line", "trust")


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

    def duckdb_from(self) -> str | None:
        """Return a DuckDB ``FROM`` expression for this source, or ``None``.

        DuckDB reads CSV, TSV, JSON, JSON Lines and Parquet (optionally gzip/zstd
        compressed) natively. Options it cannot apply — a named sheet or table, nested
        flattening, ``--on-error skip|warn``, XML tags — force the Python reader.
        """
        from ..constants import DUCKABLE_CODECS, DUCKABLE_FILE_TYPES

        if "://" in self.path or not os.path.isfile(self.path):
            return None
        if any(self.options.get(key) for key in _PYTHON_ONLY_OPTIONS):
            return None
        if self.options.get("on_error") in ("skip", "warn"):
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
