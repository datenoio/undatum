"""Column types for ``--create-table``, inferred from a batch of records.

Values from text formats arrive as strings, so a string column whose values all look like
integers (or numbers, or true/false) gets that type. Each backend maps the kinds to its own
SQL types.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

SAMPLE_ROWS = 1000
_INTEGER = re.compile(r"^[+-]?[0-9]{1,18}$")
_NUMBER = re.compile(r"^[+-]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][+-]?[0-9]+)?$")
_BOOLEAN = {"true", "false"}

CLICKHOUSE_TYPES = {
    "integer": "Int64",
    "number": "Float64",
    "boolean": "Bool",
    "datetime": "DateTime64(6)",
    "date": "Date32",
    "string": "String",
}
MSSQL_TYPES = {
    "integer": "BIGINT",
    "number": "FLOAT",
    "boolean": "BIT",
    "datetime": "DATETIME2",
    "date": "DATE",
    "string": "NVARCHAR(MAX)",
}


def _kind(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, dt.datetime):
        return "datetime"
    if isinstance(value, dt.date):
        return "date"
    if isinstance(value, str):
        text = value.strip()
        digits = text.lstrip("+-")
        if len(digits) > 1 and digits.startswith("0") and digits[1].isdigit():
            return "string"  # codes such as 007 keep their leading zeros
        if _INTEGER.match(text):
            return "integer"
        if _NUMBER.match(text):
            return "number"
        if text.lower() in _BOOLEAN:
            return "boolean"
    return "string"


def infer_kinds(batch: list[dict[str, Any]]) -> list[tuple[str, str, bool]]:
    """``(column, kind, nullable)`` in first-seen order from up to ``SAMPLE_ROWS`` records.

    Mixed integer and number values become number; any other mix becomes string.
    """
    order: dict[str, None] = {}
    kinds: dict[str, set[str]] = {}
    nullable: dict[str, bool] = {}
    sample = batch[:SAMPLE_ROWS]
    for record in sample:
        for key in record:
            order.setdefault(key, None)
    for key in order:
        seen = set()
        for record in sample:
            kind = _kind(record.get(key))
            if kind is None:
                nullable[key] = True
            else:
                seen.add(kind)
        kinds[key] = seen
    columns = []
    for key in order:
        seen = kinds[key]
        if not seen:
            kind = "string"
        elif len(seen) == 1:
            kind = next(iter(seen))
        elif seen <= {"integer", "number"}:
            kind = "number"
        else:
            kind = "string"
        columns.append((key, kind, nullable.get(key, False)))
    return columns


def convert(value: Any, kind: str) -> Any:
    """``value`` as the Python type the driver expects for ``kind`` (``None`` for empty)."""
    if value is None or value == "":
        return None
    try:
        if kind == "integer":
            return int(value)
        if kind == "number":
            return float(value)
        if kind == "boolean":
            return value if isinstance(value, bool) else str(value).strip().lower() == "true"
        if kind == "datetime" and isinstance(value, str):
            return dt.datetime.fromisoformat(value)
        if kind == "date" and isinstance(value, str):
            return dt.date.fromisoformat(value)
    except ValueError:
        return None
    if kind == "string" and not isinstance(value, str):
        import json

        return (
            json.dumps(value, ensure_ascii=False, default=str)
            if isinstance(value, (dict, list))
            else str(value)
        )
    return value
