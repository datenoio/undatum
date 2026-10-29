"""The Python engine's reader of spreadsheets: iterabledata's interface over fastexcel tables.

A separate module so that the DuckDB path, which only needs :mod:`undatum.io.excel`, does not
import iterabledata.
"""

from __future__ import annotations

from typing import Any

from iterable.base import BaseIterable

from .excel import excel_format, excel_table, sheet_names

_BATCH_ROWS = 10_000


class ExcelIterable(BaseIterable):
    """Records of one sheet of an xlsx, xlsm, xls, xlsb or ods workbook (read only).

    Args:
        filename: Workbook path.
        options: Reader options (``table``, ``page``, ``start_line``; see
            :func:`~undatum.io.excel.excel_table`).
    """

    def __init__(self, filename: str | None = None, options: dict[str, Any] | None = None):
        super().__init__()
        self.filename = filename
        self.options = dict(options or {})
        self.table: Any = None
        if filename is not None:
            self.reset()

    def reset(self) -> None:
        if self.table is None and self.filename is not None:
            self.table = excel_table(self.filename, self.options)
        self.keys = list(self.table.column_names) if self.table is not None else []
        self._batches = (
            iter(self.table.to_batches(_BATCH_ROWS)) if self.table is not None else iter(())
        )
        self._rows: list[dict[str, Any]] = []
        self._pos = 0

    @staticmethod
    def id() -> str:
        return "xlsx"

    @staticmethod
    def has_totals() -> bool:
        return True

    def totals(self) -> int:
        return int(self.table.num_rows) if self.table is not None else 0

    @staticmethod
    def has_tables() -> bool:
        return True

    def list_tables(self, filename: str | None = None) -> list[str] | None:
        path = filename or self.filename
        return sheet_names(path) if path and excel_format(path) else None

    @staticmethod
    def is_flatonly() -> bool:
        return True

    def read(self, skip_empty: bool = True) -> dict[str, Any]:
        while self._pos >= len(self._rows):
            batch = next(self._batches)  # StopIteration ends the records
            self._rows = batch.to_pylist()
            self._pos = 0
        row = self._rows[self._pos]
        self._pos += 1
        return row

    def read_bulk(self, num: int = _BATCH_ROWS) -> list[dict[str, Any]]:
        chunk: list[dict[str, Any]] = []
        while len(chunk) < num:
            try:
                chunk.append(self.read())
            except StopIteration:
                break
        return chunk

    def close(self) -> None:
        self.table = None
        self._batches = iter(())
        self._rows = []
        self._closed = True

    def __enter__(self) -> ExcelIterable:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
