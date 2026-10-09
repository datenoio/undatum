"""SQL expressions evaluated by DuckDB: row filters (``--where``) and computed columns (``--add``).

Expressions see typed values. Text columns (all CSV columns, text in other formats) are given
the first type of BIGINT, DOUBLE, DATE, TIMESTAMP, BOOLEAN that at least 95% of their non-empty
sampled values convert to; values that do not convert are NULL in the expression. Codes with
leading zeros (``007``) stay text. Output keeps the original text of existing columns, so
``--where`` never changes values it does not compute.

DuckDB-readable sources run as one query; other sources are evaluated in batches of records
registered as Arrow tables, with the same typing, so both engines agree.

Expressions may use any scalar SQL function except ``getenv`` / ``current_setting``; subqueries
and table functions are rejected (an expression cannot read other files).
"""

from __future__ import annotations

import itertools
import json
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from difflib import get_close_matches
from typing import Any

from ..common.errors import ValidationError
from .base import Operation, Streaming, quote, register

TYPE_CANDIDATES = ("BIGINT", "DOUBLE", "DATE", "TIMESTAMP", "BOOLEAN")
MIN_TYPED_SHARE = 0.95
SAMPLE_ROWS = 10_000
BATCH_ROWS = 10_000
RAW = "__undatum_raw"
INDEX = "__undatum_i"
DENIED_FUNCTIONS = {"getenv", "current_setting", "query", "query_table"}

_ADD = re.compile(r'^\s*("(?:[^"]|"")+"|[A-Za-z_][A-Za-z0-9_]*)\s*=(?!=)\s*(.+?)\s*$', re.S)
_MISSING_COLUMN = re.compile(r'Referenced column "?([^"\s]+)"? not found')


@dataclass(frozen=True)
class WhereConfig:
    """Keep the records matching a SQL condition and add computed columns.

    Args:
        where: SQL boolean expression evaluated by DuckDB, e.g.
            ``amount > 100 AND city = 'Berlin'``.
        add: Computed columns as ``name = SQL expression``, e.g. ``total = price * qty``;
            a name that exists replaces that column in place.
    """

    where: str | None = None
    add: tuple[str, ...] = field(default=())


def parse_add(spec: str) -> tuple[str, str]:
    """``"total = price * qty"`` -> ``("total", "price * qty")``.

    Raises:
        ValidationError: If ``spec`` is not ``name = expression``.
    """
    match = _ADD.match(spec)
    if not match:
        raise ValidationError(f"--add expects 'name = expression', got {spec!r}", field="add")
    name = match.group(1)
    if name.startswith('"'):
        name = name[1:-1].replace('""', '"')
    return name, match.group(2)


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def check_expression(conn: Any, expression: str, option: str) -> None:
    """Reject anything but one scalar expression (no subqueries, table functions, getenv).

    Raises:
        ValidationError: If the expression does not parse or is not allowed.
    """
    raw = conn.sql("SELECT json_serialize_sql(?)", params=[f"SELECT {expression}"]).fetchone()[0]
    tree = json.loads(raw)
    if tree.get("error") or len(tree.get("statements") or []) != 1:
        message = tree.get("error_message") or "not a single expression"
        raise ValidationError(
            f"Invalid {option} expression {expression!r}: {message}", field=option
        )
    problems: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("class") == "SUBQUERY" or node.get("type") == "SUBQUERY":
                problems.add("subqueries")
            name = str(node.get("function_name") or "").lower()
            if name in DENIED_FUNCTIONS or name.startswith("read_"):
                problems.add(f"{name}()")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(tree["statements"][0].get("node", {}).get("select_list"))
    if problems:
        raise ValidationError(
            f"{option} expression {expression!r} may not use {', '.join(sorted(problems))}",
            field=option,
        )


def infer_types(
    conn: Any, relation: str, schema: dict[str, str], min_share: float = MIN_TYPED_SHARE
) -> dict[str, str]:
    """Types for text columns: the first type ``min_share`` of their values convert to.

    Args:
        conn: DuckDB connection.
        relation: Relation (table function or subquery) with the columns.
        schema: Column -> DuckDB type; only ``VARCHAR`` columns are inferred.
        min_share: Share of non-empty sampled values that must convert (1.0: all).
    """
    text = [name for name, kind in schema.items() if kind == "VARCHAR"]
    types = dict(schema)
    if not text:
        return types
    parts = []
    for name in text:
        value = _value_sql(quote(name))
        parts += [
            f"count({value})",
            # TRY_CAST('1.5' AS BIGINT) rounds, so integers are matched by pattern.
            f"count_if(regexp_matches({value}, '^[+-]?[0-9]{{1,18}}$'))",
            f"count(TRY_CAST({value} AS DOUBLE))",
            f"count_if(TRY_CAST({value} AS DATE) IS NOT NULL"
            f" AND NOT regexp_matches({value}, '[0-9]:[0-9]'))",
            f"count(TRY_CAST({value} AS TIMESTAMP))",
            f"count_if(lower({value}) IN ('true', 'false'))",
            f"count_if(regexp_matches({value}, '^[+-]?0[0-9]'))",
        ]
    sample = f"(SELECT * FROM {relation} LIMIT {SAMPLE_ROWS})"
    counts = conn.sql(f"SELECT {', '.join(parts)} FROM {sample}").fetchone()
    for index, name in enumerate(text):
        total, *typed, leading_zero = counts[index * 7 : index * 7 + 7]
        if not total or leading_zero:
            continue
        for kind, converted in zip(TYPE_CANDIDATES, typed, strict=True):
            if converted >= total * min_share:
                types[name] = kind
                break
    return types


# Placeholders that mean "no value" in text data.
NULL_TOKENS = ("", "na", "n/a", "null", "none", "nan", "-")


def _value_sql(column: str) -> str:
    """The value of a text column for typing: trimmed, NULL for placeholders."""
    tokens = ", ".join(_literal(token) for token in NULL_TOKENS)
    return f"CASE WHEN lower(trim({column})) IN ({tokens}) THEN NULL ELSE trim({column}) END"


def build_query(
    relation: str,
    schema: dict[str, str],
    types: dict[str, str],
    cfg: WhereConfig,
    *,
    index_only: bool = False,
) -> str:
    """The DuckDB query of ``cfg`` over ``relation``.

    With ``index_only`` the query returns the ``__undatum_i`` column of ``relation`` and the
    computed columns (the Python engine merges them into the original records).
    """
    retyped = [name for name in schema if types[name] != schema[name]]
    raw_key = {name: f"c{i}" for i, name in enumerate(retyped)}
    inner_columns = [INDEX] if index_only else []
    for name in schema:
        if name in raw_key:
            value = _value_sql(quote(name))
            inner_columns.append(f"TRY_CAST({value} AS {types[name]}) AS {quote(name)}")
        else:
            inner_columns.append(quote(name))
    if raw_key and not index_only:
        struct = ", ".join(f"{_literal(key)}: {quote(name)}" for name, key in raw_key.items())
        inner_columns.append(f"{{{struct}}} AS {RAW}")
    inner = f"SELECT {', '.join(inner_columns)} FROM {relation}"

    added = dict(parse_add(spec) for spec in cfg.add)
    if index_only:
        outputs = [INDEX] + [f"({expr}) AS {quote(name)}" for name, expr in added.items()]
    else:
        outputs = []
        for name in schema:
            if name in added:
                outputs.append(f"({added[name]}) AS {quote(name)}")
            elif name in raw_key:
                outputs.append(f"{RAW}.{raw_key[name]} AS {quote(name)}")
            else:
                outputs.append(quote(name))
        outputs += [
            f"({expr}) AS {quote(name)}" for name, expr in added.items() if name not in schema
        ]
    query = f"SELECT {', '.join(outputs)} FROM ({inner}) AS __undatum_typed"
    if cfg.where:
        query += f" WHERE ({cfg.where})"
    if index_only:
        query += f" ORDER BY {INDEX}"
    return query


def validate(conn: Any, types: dict[str, str], cfg: WhereConfig) -> None:
    """Check the expressions against the columns (unknown names, type errors) up front.

    Raises:
        ValidationError: With the closest column names as suggestions.
    """
    import duckdb

    for spec in cfg.add:
        check_expression(conn, parse_add(spec)[1], "--add")
    if cfg.where:
        check_expression(conn, cfg.where, "--where")
    columns = ", ".join(f"NULL::{kind} AS {quote(name)}" for name, kind in types.items())
    empty = f"(SELECT {columns or 'NULL AS __undatum_none'} LIMIT 0)"
    try:
        conn.sql(build_query(empty, types, types, cfg)).fetchall()
    except duckdb.Error as exc:
        message = str(exc).splitlines()[0]
        missing = _MISSING_COLUMN.search(str(exc))
        suggestions = get_close_matches(missing.group(1), list(types), n=3) if missing else None
        text_columns = [name for name, kind in types.items() if kind == "VARCHAR"]
        if "VARCHAR" in message and text_columns:
            message += (
                f". Text columns (not every value is a number or date): {', '.join(text_columns)};"
                " cast them, e.g. TRY_CAST(column AS DOUBLE)"
            )
        raise ValidationError(
            f"Invalid expression: {message}",
            field="where" if cfg.where else "add",
            suggestions=suggestions or None,
        ) from exc


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


@register
class Where(Operation[WhereConfig]):
    """SQL row filter and computed columns (DuckDB expressions)."""

    name = "where"
    streaming = Streaming.ROW

    def apply(self, rows: Iterable[Any], cfg: WhereConfig) -> Iterator[Any]:
        import duckdb
        import pyarrow as pa

        conn = duckdb.connect()
        conn.execute("SET threads = 1")
        try:
            columns: list[str] = []
            types: dict[str, str] | None = None
            iterator = iter(rows)
            while True:
                batch = list(itertools.islice(iterator, BATCH_ROWS))
                if not batch:
                    return
                records = [row for row in batch if isinstance(row, dict)]
                for row in records:
                    for key in row:
                        if key not in columns:
                            columns.append(key)
                arrays: dict[str, list[Any]] = {INDEX: list(range(len(records)))}
                arrays.update(
                    {
                        f"c{i}": [_text(r.get(name)) for r in records]
                        for i, name in enumerate(columns)
                    }
                )
                table = pa.table(
                    {
                        k: pa.array(v, type=pa.string()) if k != INDEX else v
                        for k, v in arrays.items()
                    }
                )
                conn.register("__undatum_batch", table)
                renamed = ", ".join(
                    [INDEX] + [f"c{i} AS {quote(n)}" for i, n in enumerate(columns)]
                )
                relation = f"(SELECT {renamed} FROM __undatum_batch)"
                schema = dict.fromkeys(columns, "VARCHAR")
                if types is None:
                    types = infer_types(conn, relation, schema)
                    validate(conn, types, cfg)
                current = {name: types.get(name, "VARCHAR") for name in columns}
                result = conn.sql(build_query(relation, schema, current, cfg, index_only=True))
                names = result.columns[1:]
                for index, *values in result.fetchall():
                    record = dict(records[index])
                    record.update(zip(names, values, strict=True))
                    yield record
                conn.unregister("__undatum_batch")
        finally:
            conn.close()

    def to_sql(self, source: str, schema: dict[str, str], cfg: WhereConfig) -> str | None:
        import duckdb

        conn = duckdb.connect()
        try:
            types = infer_types(conn, source, schema)
            validate(conn, types, cfg)
        finally:
            conn.close()
        return build_query(source, schema, types, cfg)


def where_steps(options: dict[str, Any] | None) -> list[tuple[str, Any]]:
    """The ``where`` step for command ``options`` (``where`` / ``add``), or ``[]``."""
    options = options or {}
    where = options.get("where") or None
    add = tuple(options.get("add") or ())
    if not where and not add:
        return []
    return [("where", WhereConfig(where=where, add=add))]
