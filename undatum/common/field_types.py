"""One set of rules for the type of a field, shared by schema, stats, quality and schema-drift.

Types use one vocabulary: ``integer``, ``number``, ``boolean``, ``date``, ``datetime``, ``time``,
``string``, ``object``, ``array``, ``binary`` and ``null`` (no values seen).

Values read as text (CSV and TSV, and inputs undatum reads as text) get the first of integer,
number, boolean, date and datetime that at least ``MIN_TYPED_SHARE`` of their non-empty values
convert to, in a sample of ``SAMPLE_ROWS`` records. Placeholders such as ``n/a`` count as empty,
a value with a leading zero (``007``) makes the field a string, and dates are ISO dates or
day-first dates (``31.12.2020``, ``31/12/2020``, ``31-12-2020``, ``2020/12/31``). Typed inputs
(JSON, Parquet) keep their own types: a JSON string stays a string.
"""

from __future__ import annotations

from typing import Any

MIN_TYPED_SHARE = 0.95
SAMPLE_ROWS = 10_000
# Placeholders that mean "no value" in text data.
NULL_TOKENS = ("", "na", "n/a", "null", "none", "nan", "-")
# Day-first dates, as in Russian and most European data (DuckDB reads ISO dates itself).
DATE_FORMATS = ("%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")
# Text types in the order they are tried.
TEXT_TYPES = ("integer", "number", "boolean", "date", "datetime")
# DuckDB types for the text types (TRY_CAST targets and schema output).
DUCKDB_TYPES = {
    "integer": "BIGINT",
    "number": "DOUBLE",
    "boolean": "BOOLEAN",
    "date": "DATE",
    "datetime": "TIMESTAMP",
    "time": "TIME",
    "string": "VARCHAR",
    "null": "VARCHAR",
}


def normalize_type(kind: str | None) -> str:
    """A DuckDB, JSON Schema or Frictionless type name as one of the normalized types."""
    text = (kind or "").strip().upper()
    if not text or text == "NULL":
        return "null"
    if text.endswith("[]") or text.startswith(("LIST", "ARRAY")):
        return "array"
    if text.startswith(("STRUCT", "MAP", "OBJECT", "JSON", "UNION")):
        return "object"
    integer = ("BIGINT", "INTEGER", "INT", "SMALLINT", "TINYINT", "HUGEINT", "UBIGINT", "UINTEGER")
    if text in integer or text in ("USMALLINT", "UTINYINT", "UHUGEINT", "INT64", "INT32", "YEAR"):
        return "integer"
    if text.startswith(("DOUBLE", "FLOAT", "REAL", "DECIMAL", "NUMERIC", "NUMBER")):
        return "number"
    if text.startswith(("BOOL",)):
        return "boolean"
    if text == "DATE":
        return "date"
    if text.startswith(("TIMESTAMP", "DATETIME", "DATE-TIME")):
        return "datetime"
    if text.startswith("TIME"):
        return "time"
    if text in ("BLOB", "BYTEA", "BINARY", "VARBINARY"):
        return "binary"
    return "string"


def quote(name: str) -> str:
    """A DuckDB identifier."""
    return '"' + name.replace('"', '""') + '"'


def literal(text: str) -> str:
    """A DuckDB string literal."""
    return "'" + text.replace("'", "''") + "'"


def value_sql(column: str) -> str:
    """The value of a text column for typing: trimmed, NULL for placeholders."""
    tokens = ", ".join(literal(token) for token in NULL_TOKENS)
    return f"CASE WHEN lower(trim({column})) IN ({tokens}) THEN NULL ELSE trim({column}) END"


def text_condition(value: str, kind: str, *, day_first_dates: bool = True) -> str:
    """SQL condition that the text ``value`` (from :func:`value_sql`) is a ``kind`` value.

    Args:
        value: SQL expression of the trimmed text value.
        kind: One of ``TEXT_TYPES``.
        day_first_dates: Also accept the ``DATE_FORMATS`` dates (``TRY_CAST`` reads ISO only).
    """
    if kind == "integer":
        # TRY_CAST('1.5' AS BIGINT) rounds, so integers are matched by pattern.
        return f"regexp_matches({value}, '^[+-]?[0-9]{{1,18}}$')"
    if kind == "number":
        return f"TRY_CAST({value} AS DOUBLE) IS NOT NULL"
    if kind == "boolean":
        return f"lower({value}) IN ('true', 'false')"
    if kind == "date":
        iso = (
            f"TRY_CAST({value} AS DATE) IS NOT NULL AND NOT regexp_matches({value}, '[0-9]:[0-9]')"
        )
        if not day_first_dates:
            return iso
        formats = ", ".join(literal(fmt) for fmt in DATE_FORMATS)
        return f"(({iso}) OR try_strptime({value}, [{formats}]) IS NOT NULL)"
    if kind == "datetime":
        return f"TRY_CAST({value} AS TIMESTAMP) IS NOT NULL"
    raise ValueError(f"Not a text type: {kind}")


def _count_sql(value: str, weight: str | None, *, day_first_dates: bool) -> list[str]:
    """Aggregates: non-empty values, values of each text type, values with a leading zero."""

    def count(condition: str) -> str:
        if weight is None:
            return f"count_if({condition})"
        return f"coalesce(sum({weight}) FILTER (WHERE {condition}), 0)"

    conditions = [f"{value} IS NOT NULL"]
    conditions += [
        text_condition(value, kind, day_first_dates=day_first_dates) for kind in TEXT_TYPES
    ]
    conditions.append(f"regexp_matches({value}, '^[+-]?0[0-9]+$')")
    return [count(condition) for condition in conditions]


def _decide(counts: tuple[Any, ...], min_share: float) -> tuple[str, bool]:
    """The type for the aggregates of :func:`_count_sql`, and whether it is a digit code."""
    present, *typed, codes = (int(count or 0) for count in counts)
    if not present:
        return "null", False
    if codes:
        # Leading zeros are kept: identifiers such as postal codes or INN, not numbers.
        return "string", typed[0] == present
    for kind, converted in zip(TEXT_TYPES, typed, strict=True):
        if converted >= present * min_share:
            return kind, False
    return "string", False


def infer_text_types(
    conn: Any,
    relation: str,
    columns: list[str],
    *,
    min_share: float = MIN_TYPED_SHARE,
    day_first_dates: bool = True,
    codes: set[str] | None = None,
) -> dict[str, str]:
    """Types of the text ``columns`` of ``relation`` from a sample of its records.

    Args:
        conn: DuckDB connection.
        relation: Table expression (table function, subquery or table name).
        columns: Text (VARCHAR) columns to type.
        min_share: Share of non-empty values that must convert (1.0: all).
        day_first_dates: Accept ``DATE_FORMATS`` dates as well as ISO dates.
        codes: Filled with the columns of digit strings with leading zeros (``007``).

    Returns:
        Column -> normalized type.
    """
    if not columns:
        return {}
    parts: list[str] = []
    for name in columns:
        parts += _count_sql(value_sql(quote(name)), None, day_first_dates=day_first_dates)
    sample = f"(SELECT * FROM {relation} LIMIT {SAMPLE_ROWS})"
    # One thread: parallel CSV readers buffer far beyond the sample (about 115 MB more for
    # `schema` on 1M rows with 14 threads), and the sample is small.
    threads = conn.execute("SELECT current_setting('threads')").fetchall()[0][0]
    conn.execute("SET threads = 1")
    try:
        row = conn.execute(f"SELECT {', '.join(parts)} FROM {sample}").fetchall()[0]
    finally:
        conn.execute(f"SET threads = {int(threads)}")
    width = len(TEXT_TYPES) + 2
    types = {}
    for index, name in enumerate(columns):
        kind, code = _decide(row[index * width : (index + 1) * width], min_share)
        types[name] = kind
        if code and codes is not None:
            codes.add(name)
    return types


def infer_value_types(
    values: dict[str, dict[Any, int]],
    *,
    min_share: float = MIN_TYPED_SHARE,
    codes: set[str] | None = None,
) -> dict[str, str]:
    """Types of fields from their distinct values and counts, with the text rules.

    For records undatum reads itself (formats DuckDB cannot read): values are typed as text.

    Args:
        values: Field -> {value: number of records}.
        min_share: Share of non-empty values that must convert.
        codes: Filled with the fields of digit strings with leading zeros.

    Returns:
        Field -> normalized type.
    """
    import duckdb
    import pyarrow as pa

    conn = duckdb.connect()
    try:
        types = {}
        for field, counts in values.items():
            items = [(str(value), int(n)) for value, n in counts.items() if value is not None]
            table = pa.table(
                {
                    "v": pa.array([item[0] for item in items], type=pa.string()),
                    "w": pa.array([item[1] for item in items], type=pa.int64()),
                }
            )
            conn.register("__values", table)
            parts = _count_sql(value_sql("v"), "w", day_first_dates=True)
            row = conn.execute(f"SELECT {', '.join(parts)} FROM __values").fetchall()[0]
            conn.unregister("__values")
            kind, code = _decide(row, min_share)
            types[field] = kind
            if code and codes is not None:
                codes.add(field)
        return types
    finally:
        conn.close()


def column_types(
    conn: Any,
    relation: str,
    *,
    text_values: bool,
    codes: set[str] | None = None,
) -> dict[str, str]:
    """Normalized types of the fields of ``relation``, struct members as dotted paths.

    Args:
        conn: DuckDB connection.
        relation: Table expression.
        text_values: The text columns hold values read as text (CSV), which are typed with
            :func:`infer_text_types`; otherwise text columns are strings.
        codes: Filled with the columns of digit strings with leading zeros.

    Returns:
        Field path -> normalized type, in column order.
    """
    types: dict[str, str] = {}
    text: list[str] = []

    def describe(parents: list[str]) -> None:
        select = ".".join(quote(part) for part in parents) + ".*" if parents else "*"
        for row in conn.execute(f"DESCRIBE SELECT {select} FROM {relation}").fetchall():
            name, kind = str(row[0]), str(row[1]).upper()
            path = ".".join([*parents, name])
            if kind == "VARCHAR" and text_values and not parents:
                text.append(name)
                types[path] = "string"  # replaced by the inferred type below
            else:
                types[path] = normalize_type(kind)
            if kind.startswith("STRUCT"):
                describe([*parents, name])

    describe([])
    types.update(infer_text_types(conn, relation, text, codes=codes))
    return types


def apply_text_types(conn: Any, relation: str, columns: list[list[Any]]) -> None:
    """Replace the DuckDB types of ``columns`` (``[name, type, ...]``) with the shared rules.

    For CSV, whose types the DuckDB sniffer guesses from its own sample; ``relation`` reads the
    file as text (``RowSource.duckdb_from()``).
    """
    types = column_types(conn, relation, text_values=True)
    for column in columns:
        kind = types.get(str(column[0]))
        if kind in DUCKDB_TYPES:
            column[1] = DUCKDB_TYPES[kind]
