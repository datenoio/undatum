"""Row counting module."""

import logging
from typing import Any

from ..common.command_utils import get_iterable_options, run_with_duckdb_fallback
from ..common.engine_selector import validate_engine
from ..common.errors import FileNotFoundError, PermissionError, find_similar_files
from ..common.path_utils import validate_file_path
from ..io import RowSource

logger = logging.getLogger(__name__)

# Formats whose row count is stored in the file, so iterabledata's ``totals()`` is exact
# without reading the rows. (Text formats count lines, which is wrong for multi-line values.)
METADATA_TOTALS = frozenset({"parquet", "orc", "arrow", "feather", "dbf"})


def count_records(fromfile: str, options: dict[str, Any] | None = None) -> int:
    """Number of records in a file.

    CSV, TSV, JSON, JSON Lines and Parquet are counted by DuckDB; formats that store
    their row count (ORC, Arrow, DBF) use it; everything else is read once.

    Args:
        fromfile: Input path.
        options: Command options (reader options, ``engine``).

    Returns:
        The record count.
    """
    options = options or {}
    source = RowSource(fromfile, options)
    engine = validate_engine(options.get("engine"))
    from ..ops.expr import where_steps

    steps = where_steps(options)
    if steps:
        return _count_where(source, steps, engine)
    expr = source.duckdb_from() if engine != "python" else None
    if engine == "duckdb" and expr is None:
        logger.info("count: DuckDB cannot read %s; reading it with iterabledata", fromfile)
    logger.debug("count: %s with %s", fromfile, "DuckDB" if expr else "iterabledata")

    def _count_duckdb() -> int:
        import duckdb

        row = duckdb.sql(f"SELECT count(*) FROM {expr}").fetchone()
        return int(row[0]) if row else 0

    return int(
        run_with_duckdb_fallback(
            "count",
            _count_duckdb,
            lambda: _count_rows(source),
            engine="duckdb" if expr else "python",
        )
    )


def _count_where(source: RowSource, steps: list[Any], engine: str) -> int:
    """Records matching ``--where`` (one DuckDB query when the input allows)."""
    from ..ops import compose_sql, get_operation

    resolved = [(get_operation(name), cfg) for name, cfg in steps]
    relation = source.duckdb_from() if engine != "python" else None
    if relation is not None:
        import duckdb

        conn = duckdb.connect()
        try:
            query = compose_sql(conn, relation, resolved)
            if query is not None:
                row = conn.sql(f"SELECT count(*) FROM ({query})").fetchone()
                return int(row[0]) if row else 0
        finally:
            conn.close()
    rows: Any = source
    for op, cfg in resolved:
        rows = op.apply(rows, cfg)
    return sum(1 for _ in rows)


def _count_rows(source: RowSource) -> int:
    options = source.options
    if source.format_id in METADATA_TOTALS and not options.get("on_error"):
        from ..common.s3_iterable import open_path

        iterable = open_path(source.path, mode="r", iterableargs=get_iterable_options(options))
        try:
            if iterable.has_totals():
                return int(iterable.totals())
        finally:
            iterable.close()
    count = 0
    for count, _ in enumerate(source, start=1):  # noqa: B007 - only the count is used
        if count % 100_000 == 0:
            logger.debug("count: processed %d records", count)
    return count


class Counter:
    """Row counting handler."""

    def count(self, fromfile, options=None):
        """Print the number of records in a data file (a number, or JSON with ``format_out``).

        Args:
            fromfile: Input path.
            options: Command options (reader options, ``engine``, ``format_out``).
        """
        options = options or {}
        try:
            validate_file_path(fromfile, check_read=True)
        except FileNotFoundError as e:
            raise FileNotFoundError(fromfile, find_similar_files(fromfile)) from e
        except PermissionError as e:
            raise PermissionError(fromfile, operation="read") from e
        count = count_records(fromfile, options)
        if str(options.get("format_out") or "").lower() == "json":
            from ..common.results import COUNT, emit

            emit(COUNT, {"file": fromfile, "rows": count})
        else:
            print(count)
