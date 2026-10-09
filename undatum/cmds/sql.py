"""Ad-hoc SQL queries over data files using DuckDB."""

import logging
import re
import sys

import orjson

from ..common.duckdb_config import create_duckdb_connection, get_duckdb_config_from_options
from ..common.errors import (
    FileNotFoundError,
    UndatumError,
    ValidationError,
    find_similar_files,
)
from ..common.path_utils import validate_file_path
from ..utils import normalize_for_json

logger = logging.getLogger(__name__)

OUTPUT_FORMATS = ["jsonl", "csv", "parquet"]


def view_name_for_file(filepath: str) -> str:
    """Derive a SQL view name from a file path.

    The file stem is sanitized to a valid SQL identifier: non-alphanumeric
    characters become underscores and a leading digit is prefixed.

    Args:
        filepath: Path to the input file.

    Returns:
        A valid DuckDB identifier.
    """
    stem = filepath.replace("\\", "/").rsplit("/", 1)[-1]
    # Strip all extensions (e.g. data.csv.gz -> data)
    stem = stem.split(".", 1)[0]
    name = re.sub(r"\W", "_", stem)
    if not name or name[0].isdigit():
        name = "t_" + name
    return name


class SqlExecutor:
    """Executes ad-hoc DuckDB SQL queries over data files."""

    def query(self, query: str, files: list, options: dict = None):
        """Run a SQL query with the given files registered as views.

        Args:
            query: SQL query text. Single-file queries can reference the
                file as the view ``data``.
            files: List of input file paths.
            options: Command options (output, format, duckdb_* settings).

        Raises:
            ValidationError: If the query or output format is invalid.
            FileNotFoundError: If an input file does not exist.
            UndatumError: If query execution fails.
        """
        if options is None:
            options = {}
        if not query or not query.strip():
            raise ValidationError("sql requires a non-empty query", field="query")
        if not files:
            raise ValidationError("sql requires at least one input file", field="files")

        output = options.get("output")
        output_format = options.get("format") or "jsonl"
        if output_format not in OUTPUT_FORMATS:
            raise ValidationError(
                f"Unsupported output format: {output_format}",
                field="format",
                suggestions=OUTPUT_FORMATS,
            )
        if output_format == "parquet" and not output:
            raise ValidationError(
                "parquet output requires --output (binary format cannot go to stdout)",
                field="output",
            )

        for filepath in files:
            try:
                validate_file_path(filepath, check_read=True)
            except FileNotFoundError as e:
                suggestions = find_similar_files(filepath)
                raise FileNotFoundError(filepath, suggestions) from e

        duckdb_config = get_duckdb_config_from_options(options)
        conn = create_duckdb_connection(**duckdb_config)
        try:
            views = self._register_views(conn, files)
            logger.debug(f"sql: registered views {views}")
            if output_format == "parquet":
                escaped = output.replace("'", "''")
                try:
                    conn.execute(f"COPY ({query}) TO '{escaped}' (FORMAT PARQUET)")
                except Exception as e:
                    raise UndatumError(f"SQL query failed: {e}") from e
                return
            try:
                result = conn.execute(query)
            except Exception as e:
                raise UndatumError(f"SQL query failed: {e}") from e
            self._write_result(result, output, output_format)
        finally:
            conn.close()

    def fetch(self, query: str, files: list, options: dict = None, max_rows: int = 500):
        """Execute SQL and return a bounded list of row dicts (no stdout).

        Args:
            query: SQL query text. Single-file queries can reference ``data``.
            files: Input file paths registered as views.
            options: DuckDB settings (same keys as ``query``).
            max_rows: Maximum rows to materialize.

        Returns:
            Tuple of ``(column_names, records, truncated)``.

        Raises:
            ValidationError: If the query, files, or ``max_rows`` are invalid.
            FileNotFoundError: If an input file does not exist.
            UndatumError: If query execution fails.
        """
        if options is None:
            options = {}
        if not query or not query.strip():
            raise ValidationError("sql requires a non-empty query", field="query")
        if not files:
            raise ValidationError("sql requires at least one input file", field="files")
        if max_rows < 1:
            raise ValidationError("max_rows must be at least 1", field="limit")

        for filepath in files:
            try:
                validate_file_path(filepath, check_read=True)
            except FileNotFoundError as e:
                suggestions = find_similar_files(filepath)
                raise FileNotFoundError(filepath, suggestions) from e

        duckdb_config = get_duckdb_config_from_options(options)
        conn = create_duckdb_connection(**duckdb_config)
        try:
            self._register_views(conn, files)
            try:
                result = conn.execute(query)
            except Exception as e:
                raise UndatumError(f"SQL query failed: {e}") from e
            description = result.description or []
            columns = [d[0] for d in description]
            raw = result.fetchmany(int(max_rows) + 1)
            truncated = len(raw) > max_rows
            records = [
                normalize_for_json(dict(zip(columns, row, strict=False))) for row in raw[:max_rows]
            ]
            return columns, records, truncated
        finally:
            conn.close()

    @staticmethod
    def _register_views(conn, files: list) -> dict:
        """Register each input file as a DuckDB view.

        Returns:
            Mapping of view name to file path.
        """
        views = {}
        for filepath in files:
            name = view_name_for_file(filepath)
            # Avoid collisions between files with the same stem
            unique = name
            i = 2
            while unique in views:
                unique = f"{name}_{i}"
                i += 1
            escaped = filepath.replace("'", "''")
            conn.execute(f"CREATE VIEW \"{unique}\" AS SELECT * FROM '{escaped}'")
            views[unique] = filepath
        if len(files) == 1 and "data" not in views:
            conn.execute(f'CREATE VIEW "data" AS SELECT * FROM "{next(iter(views))}"')
        return views

    @staticmethod
    def _write_result(result, output, output_format):
        """Write a DuckDB result to the requested output destination."""
        columns = [d[0] for d in result.description]
        if output_format == "csv":
            import csv

            out = open(output, "w", encoding="utf8", newline="") if output else sys.stdout
            try:
                writer = csv.writer(out)
                writer.writerow(columns)
                while True:
                    rows = result.fetchmany(10000)
                    if not rows:
                        break
                    writer.writerows(rows)
            finally:
                if output:
                    out.close()
            return

        # jsonl
        out = open(output, "wb") if output else sys.stdout.buffer
        try:
            while True:
                rows = result.fetchmany(10000)
                if not rows:
                    break
                for row in rows:
                    record = normalize_for_json(dict(zip(columns, row, strict=False)))
                    out.write(
                        orjson.dumps(
                            record,
                            option=orjson.OPT_APPEND_NEWLINE | orjson.OPT_SERIALIZE_NUMPY,
                            default=str,
                        )
                    )
        finally:
            if output:
                out.close()
