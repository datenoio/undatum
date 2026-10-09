"""Run an operation on a source with the best engine and write the result."""

from __future__ import annotations

import itertools
import logging
from collections.abc import Iterator, Sequence
from typing import Any

from ..common.engine_selector import validate_engine
from ..io import RowSource, open_sink
from .base import REGISTRY, Operation

logger = logging.getLogger(__name__)

BATCH_ROWS = 10_000
DEFAULT_DUCKDB_MEMORY = "256MB"


def get_operation(name: str) -> Operation[Any]:
    """Return the registered operation called ``name``."""
    from . import expr, query, rows, structure  # noqa: F401 - registers the built-in operations

    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"Unknown operation '{name}'. Known: {', '.join(sorted(REGISTRY))}"
        ) from None


def run(
    operation: str | Operation[Any],
    cfg: Any,
    source: RowSource,
    output: str | None = None,
    *,
    engine: str | None = "auto",
    format_out: str | None = None,
    fieldnames: list[str] | None = None,
) -> int:
    """Apply ``operation`` to ``source`` and write the records to ``output`` (or stdout).

    With ``engine`` ``auto`` the operation runs as one DuckDB query when the source is
    DuckDB-readable and the operation has a SQL form; otherwise rows stream through the
    Python implementation. ``duckdb`` and ``python`` force a choice (``duckdb`` still falls
    back to Python, with a warning, when there is no SQL form or DuckDB fails).

    Args:
        operation: Operation instance or registered name.
        cfg: The operation's configuration dataclass.
        source: Input rows.
        output: Output path or URI; stdout when empty.
        engine: ``auto``, ``duckdb`` or ``python``.
        format_out: Explicit output format.
        fieldnames: Column order for flat formats (Python engine).

    Returns:
        Number of records written (``-1`` when DuckDB wrote a file and did not report it).
    """
    return run_steps(
        [(operation, cfg)],
        source,
        output,
        engine=engine,
        format_out=format_out,
        fieldnames=fieldnames,
    )


def run_steps(
    steps: Sequence[tuple[str | Operation[Any], Any]],
    source: RowSource,
    output: str | None = None,
    *,
    engine: str | None = "auto",
    format_out: str | None = None,
    fieldnames: list[str] | None = None,
) -> int:
    """Apply several operations in order (one DuckDB query when every step has a SQL form).

    Args:
        steps: ``(operation, config)`` pairs, applied first to last.
        source: Input rows.
        output: Output path or URI; stdout when empty.
        engine: ``auto``, ``duckdb`` or ``python``.
        format_out: Explicit output format.
        fieldnames: Column order for flat formats (Python engine).

    Returns:
        Number of records written (``-1`` when DuckDB wrote a file and did not report it).
    """
    resolved = [(get_operation(op) if isinstance(op, str) else op, cfg) for op, cfg in steps]
    engine = validate_engine(engine)
    if engine != "python":
        written = _run_sql(resolved, source, output, format_out, required=engine == "duckdb")
        if written is not None:
            return written
    names = " | ".join(op.name for op, _ in resolved)
    logger.debug("%s: Python engine", names)
    # The source itself (not an iterator) so two-pass operations can read it again.
    rows: Any = source
    for op, cfg in resolved:
        rows = op.apply(rows, cfg)
    return write_rows(iter(rows), output, format_out=format_out, fieldnames=fieldnames)


def compose_sql(conn: Any, relation: str, steps: list[tuple[Operation[Any], Any]]) -> str | None:
    """One DuckDB query applying ``steps`` to ``relation``, or ``None`` without a SQL form."""
    query = f"SELECT * FROM {relation}"
    source = relation
    for op, cfg in steps:
        described = conn.sql(f"DESCRIBE SELECT * FROM {source}").fetchall()
        schema = {row[0]: str(row[1]).upper() for row in described}
        sql = op.to_sql(source, schema, cfg)
        if sql is None:
            return None
        query = sql
        source = f"({query})"
    return query


def write_rows(
    rows: Iterator[Any],
    output: str | None,
    *,
    format_out: str | None = None,
    fieldnames: list[str] | None = None,
) -> int:
    """Write ``rows`` in batches to ``output`` (or stdout); remove a partial file on error."""
    from ..utils import normalize_for_json

    sink = open_sink(output, format_out=format_out, fieldnames=fieldnames)
    count = 0
    try:
        while True:
            batch = [
                normalize_for_json(row) if isinstance(row, dict) else row
                for row in itertools.islice(rows, BATCH_ROWS)
            ]
            if not batch:
                break
            sink.write_batch(batch)
            count += len(batch)
    except BaseException:
        sink.abort()
        raise
    sink.close()
    return count


def _run_sql(
    steps: list[tuple[Operation[Any], Any]],
    source: RowSource,
    output: str | None,
    format_out: str | None,
    *,
    required: bool,
) -> int | None:
    """Run ``steps`` in DuckDB; return the record count, or ``None`` to use Python."""
    names = " | ".join(op.name for op, _ in steps)
    relation = source.duckdb_from()
    if relation is None:
        if required:
            logger.info("%s: input is not DuckDB-readable; using the Python engine", names)
        return None
    try:
        import duckdb

        from ..common.duckdb_config import create_duckdb_connection, get_duckdb_config_from_options

        config = get_duckdb_config_from_options(source.options)
        # Row transforms are I/O bound: one thread is nearly as fast and, with insertion
        # order preserved, avoids per-thread buffers that grow with the input. DuckDB
        # spills to disk above the memory limit.
        config.setdefault("threads", 1)
        if not config.get("memory"):
            config["memory"] = DEFAULT_DUCKDB_MEMORY
        conn = create_duckdb_connection(**config)
        try:
            query = compose_sql(conn, relation, steps)
            if query is None:
                if required:
                    logger.info("%s has no DuckDB form; using the Python engine", names)
                return None
            logger.debug("%s: DuckDB engine: %s", names, query)
            return write_query(conn, query, output, format_out)
        finally:
            conn.close()
    except (duckdb.Error, ValueError) as exc:
        logger.warning("DuckDB %s failed, falling back to the Python engine: %s", names, exc)
        return None


# DuckDB's COPY formats these differently from Python's isoformat(); such results are
# fetched and written by the Python writer so both engines produce the same text.
_TEMPORAL = ("DATE", "TIME", "TIMESTAMP", "INTERVAL")
_COPY_FORMATS = ("csv", "parquet")


def write_query(conn: Any, query: str, output: str | None, format_out: str | None = None) -> int:
    """Write the result of a DuckDB ``query`` to ``output`` (or stdout) in batches.

    CSV and Parquet files are written with ``COPY`` (returns ``-1``: count not reported);
    other outputs are fetched in batches and written by the Python writer.
    """
    from ..common.writer import duckdb_copy_to_file, resolve_output_format

    result_types = [str(row[1]).upper() for row in conn.sql(f"DESCRIBE {query}").fetchall()]
    temporal = any(t.startswith(_TEMPORAL) for t in result_types)
    if output and "://" not in output and not temporal:
        fmt = resolve_output_format(output, format_out)
        native = resolve_output_format(output) if format_out else fmt
        # COPY is used for CSV and Parquet; JSON goes through the Python writer so the
        # text is the same on both engines (DuckDB writes compact JSON).
        if fmt == native and fmt in _COPY_FORMATS and duckdb_copy_to_file(conn, query, output):
            return -1
    relation = conn.sql(query)
    names = relation.columns

    def rows() -> Iterator[dict[str, Any]]:
        while True:
            chunk = relation.fetchmany(BATCH_ROWS)
            if not chunk:
                return
            for values in chunk:
                yield dict(zip(names, values, strict=False))

    return write_rows(rows(), output, format_out=format_out, fieldnames=list(names))
