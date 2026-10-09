"""Database dump command — export tables/queries to files."""

from __future__ import annotations

import logging

from ..common.errors import ValidationError
from .db_query import DatabaseQueryExecutor

logger = logging.getLogger(__name__)


class DatabaseDumper:
    """Export database tables or queries to file formats."""

    def dump(
        self,
        db_uri: str,
        output: str,
        table: str | None = None,
        query: str | None = None,
        output_format: str = "parquet",
        batch_size: int = 10000,
    ) -> None:
        """Dump a table or query result to a file.

        Args:
            db_uri: Database connection URI.
            output: Output file path.
            table: Table name to dump (mutually exclusive with query).
            query: SQL query to dump (mutually exclusive with table).
            output_format: Output format (parquet, csv, jsonl).
            batch_size: Streaming batch size.
        """
        if not table and not query:
            raise ValidationError(
                "Either --table or --query is required for db dump",
                field="table",
            )
        if table and query:
            raise ValidationError(
                "Provide only one of --table or --query",
                field="table",
            )

        sql = query if query else f"SELECT * FROM {table}"
        fmt = (output_format or "parquet").lower()
        if fmt == "json":
            fmt = "jsonl"

        logger.info("Dumping to %s (%s)", output, fmt)
        executor = DatabaseQueryExecutor()
        executor.query(sql, db_uri, output=output, output_format=fmt, batch_size=batch_size)
        logger.info("Dump completed: %s", output)
