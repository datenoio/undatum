"""Excel and OpenDocument spreadsheets read with fastexcel, as typed Arrow tables.

One normalized Arrow table per sheet feeds both engines: DuckDB scans it
(:meth:`~undatum.io.source.RowSource.arrow_reader`) and the Python engine iterates its rows
(:class:`ExcelIterable`, opened by ``s3_iterable.open_iterable``), so they give the same records.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Extension -> format id (iterabledata's ids; xlsm workbooks are xlsx).
EXCEL_EXTENSIONS = {"xlsx": "xlsx", "xlsm": "xlsx", "xls": "xls", "xlsb": "xlsb", "ods": "ods"}
EXCEL_FORMATS = frozenset(EXCEL_EXTENSIONS.values())


def excel_format(path: str, options: dict[str, Any] | None = None) -> str | None:
    """The spreadsheet format of a local, uncompressed file, or ``None``.

    Args:
        path: File path.
        options: Reader options; ``format`` (``--format-in``) wins over the extension.
    """
    if "://" in path or not os.path.isfile(path):
        return None
    explicit = str((options or {}).get("format") or "").lower()
    if explicit:
        return explicit if explicit in EXCEL_FORMATS else None
    return EXCEL_EXTENSIONS.get(path.rsplit(".", 1)[-1].lower())


def sheet_names(path: str) -> list[str]:
    """Names of the sheets of a workbook, in order."""
    import fastexcel

    return list(fastexcel.read_excel(path).sheet_names)


def excel_table(path: str, options: dict[str, Any] | None = None) -> Any:
    """The records of one sheet as a normalized ``pyarrow.Table``.

    Column types come from every row (fastexcel's default sample of 1000 rows would turn later
    values of another type into nulls). Columns of whole numbers become integers and timestamps
    that are all at midnight become dates (Excel stores only floating-point numbers and
    timestamps); a column of mixed types is text.

    Args:
        path: Workbook path.
        options: Reader options: ``table`` (sheet name), ``page`` (sheet index, default 0),
            ``start_line`` (rows before the header).
    """
    import fastexcel

    options = options or {}
    sheet: int | str = options.get("table") or int(options.get("page") or 0)
    # fastexcel logs a warning for every column of mixed types, which is read as text.
    logging.getLogger("fastexcel").setLevel(logging.ERROR)
    loaded = fastexcel.read_excel(path).load_sheet(
        sheet,
        header_row=int(options.get("start_line") or 0),
        schema_sample_rows=None,
    )
    return normalize_table(loaded.to_arrow())


def normalize_table(table: Any) -> Any:
    """Whole-number float columns as integers, midnight-only timestamp columns as dates."""
    import pyarrow as pa
    import pyarrow.compute as pc

    columns = []
    for column in table.columns:
        kind = column.type
        if pa.types.is_floating(kind) and column.null_count < len(column):
            # Only Arrow values here: converting a Python value makes pyarrow import pandas
            whole = pc.and_kleene(pc.is_finite(column), pc.equal(pc.floor(column), column))
            if pc.all(whole).as_py():
                try:
                    column = column.cast(pa.int64())  # safe: fails beyond the int64 range
                except pa.ArrowInvalid:
                    pass
        elif pa.types.is_timestamp(kind) and column.null_count < len(column):
            dates = column.cast(pa.date32())
            if pc.all(pc.equal(dates.cast(kind), column)).as_py():
                column = dates
        columns.append(column)
    return pa.table(columns, names=table.column_names)


def open_excel(path: str, iterableargs: dict[str, Any] | None = None) -> Any | None:
    """An iterabledata-style reader of a spreadsheet's records, or ``None`` for other files."""
    if excel_format(path, iterableargs) is None:
        return None
    from .excel_iterable import ExcelIterable

    return ExcelIterable(path, options=iterableargs)
