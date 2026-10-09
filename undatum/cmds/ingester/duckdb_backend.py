"""DuckDB ingester backend."""

import logging
import time

import duckdb

from .base import INITIAL_RETRY_DELAY, MAX_RETRIES, BasicIngester

logger = logging.getLogger(__name__)


class DuckDBIngester(BasicIngester):
    """DuckDB data ingester.

    Handles bulk ingestion of records to DuckDB with COPY FROM for maximum
    performance, Appender API for streaming, and schema management. DuckDB is
    an embedded analytical database, so no separate server is required.

    Args:
        uri: DuckDB connection URI (duckdb:///path/to/db.db or duckdb:///:memory:)
        table: Table name
        mode: Ingestion mode: 'append', 'replace', or 'upsert' (default: 'append')
        create_table: If True, auto-create table from data schema (default: False)
        upsert_key: Field name(s) to use for conflict resolution in upsert mode
        use_appender: If True, use Appender API instead of COPY FROM (default: False)
    """

    def __init__(
        self, uri, table, mode="append", create_table=False, upsert_key=None, use_appender=False
    ):
        self.uri = uri
        self.table = table
        self.mode = mode
        self.create_table = create_table
        self.upsert_key = upsert_key
        self.use_appender = use_appender

        # Parse connection string
        db_path = self._parse_uri(uri)

        # Connect to DuckDB (file-based or in-memory)
        if db_path == ":memory:" or db_path is None:
            self.conn = duckdb.connect(":memory:")
            self.is_memory = True
        else:
            self.conn = duckdb.connect(db_path)
            self.is_memory = False

        self._schema_created = False
        self._table_columns = None
        self._first_batch_processed = False
        self._appender = None
        self._replace_per_call = True

    def _parse_uri(self, uri):
        """Parse DuckDB connection URI into database path.

        Supports:
        - duckdb:///path/to/db.db
        - duckdb:///:memory:
        - duckdb:///path/to/db.db (with absolute path)
        """
        if uri.startswith("duckdb:///"):
            path = uri.replace("duckdb:///", "")
            if path == ":memory:":
                return ":memory:"
            return path
        elif uri.startswith("duckdb://"):
            # Handle duckdb://:memory: format
            path = uri.replace("duckdb://", "")
            if path == ":memory:":
                return ":memory:"
            return path
        else:
            # Assume it's a direct path
            return uri

    def _infer_schema(self, batch):
        """Infer DuckDB schema from a sample batch of records.

        Analyzes multiple records to determine the best type for each column.
        DuckDB types: BOOLEAN, BIGINT, DOUBLE, VARCHAR, DATE, TIMESTAMP, etc.
        """
        if not batch:
            return []

        # Analyze all records to determine types
        column_types = {}
        sample_size = min(len(batch), 100)  # Sample up to 100 records

        for record in batch[:sample_size]:
            for key, value in record.items():
                if key not in column_types:
                    column_types[key] = []
                column_types[key].append(value)

        schema = []
        for key, values in column_types.items():
            # Determine type from non-None values
            non_null_values = [v for v in values if v is not None]

            if not non_null_values:
                duckdb_type = "VARCHAR"  # Default if all nulls
            elif all(isinstance(v, bool) for v in non_null_values):
                duckdb_type = "BOOLEAN"
            elif all(isinstance(v, int) for v in non_null_values):
                duckdb_type = "BIGINT"
            elif all(isinstance(v, float) for v in non_null_values):
                duckdb_type = "DOUBLE"
            elif all(isinstance(v, str) for v in non_null_values):
                # Try to detect date/timestamp patterns
                date_count = 0
                timestamp_count = 0
                for v in non_null_values[:10]:  # Check first 10
                    if len(v) == 10 and "-" in v and v.count("-") == 2:
                        date_count += 1
                    elif len(v) > 10 and ("T" in v or " " in v) and ("-" in v or ":" in v):
                        timestamp_count += 1

                if timestamp_count > date_count:
                    duckdb_type = "TIMESTAMP"
                elif date_count > 0:
                    duckdb_type = "DATE"
                else:
                    # Use VARCHAR
                    duckdb_type = "VARCHAR"
            else:
                # Mixed types, default to VARCHAR
                duckdb_type = "VARCHAR"

            schema.append((key, duckdb_type))

        return schema

    def _create_table(self, schema):
        """Create table from inferred schema."""
        # Check if table exists
        try:
            self.conn.execute(f"SELECT COUNT(*) FROM {self.table}").fetchone()
            table_exists = True
        except Exception:
            table_exists = False

        if table_exists:
            if self.mode == "replace":
                # Drop and recreate
                self.conn.execute(f"DROP TABLE IF EXISTS {self.table}")
            else:
                # Table exists and not replacing, just validate schema matches
                logger.info(f"Table {self.table} already exists, skipping creation")
                self._schema_created = True
                self._table_columns = [col for col, _ in schema]
                return

        # Build CREATE TABLE statement
        column_defs = [f'"{col}" {duckdb_type}' for col, duckdb_type in schema]
        constraints = []
        if self.mode == "upsert" and self.upsert_key:
            conflict_keys = (
                [self.upsert_key] if isinstance(self.upsert_key, str) else self.upsert_key
            )
            conflict_target = ", ".join([f'"{key}"' for key in conflict_keys])
            constraints.append(f"UNIQUE ({conflict_target})")
        columns = ", ".join(column_defs + constraints)
        create_sql = f"CREATE TABLE IF NOT EXISTS {self.table} ({columns})"

        self.conn.execute(create_sql)

        self._schema_created = True
        self._table_columns = [col for col, _ in schema]
        logger.info(
            f"Created table {self.table} with schema: {', '.join([f'{col} {duckdb_type}' for col, duckdb_type in schema])}"
        )

    def _validate_schema(self, batch):
        """Validate that batch schema matches table schema.

        Returns True if schema matches, False otherwise.
        Logs warnings for mismatches but allows continuation.
        """
        if not batch:
            return True

        # Get table columns
        try:
            result = self.conn.execute(f"DESCRIBE {self.table}").fetchall()
            table_schema = {row[0]: row[1] for row in result}
        except Exception:
            logger.warning(f"Table {self.table} does not exist or cannot be described")
            return False

        if not table_schema:
            return False

        # Check batch columns match
        batch_columns = set(batch[0].keys())
        table_columns = set(table_schema.keys())

        if batch_columns != table_columns:
            missing = batch_columns - table_columns
            extra = table_columns - batch_columns
            if missing:
                logger.warning(f"Batch columns not in table {self.table}: {missing}")
            if extra:
                logger.warning(f"Table columns not in batch: {extra}")
            # Allow continuation but warn
            return len(missing) == 0  # Only fail if batch has extra columns

        return True

    def _copy_from_csv(self, batch):
        """Use batch INSERT for fast bulk loading (DuckDB optimized).

        Note: DuckDB's COPY FROM requires file paths, so for in-memory batches
        we use optimized executemany which is still very fast.
        """
        # For DuckDB, executemany with batch inserts is highly optimized
        # and performs similarly to COPY FROM for reasonable batch sizes
        self._insert_batch(batch)

    def _insert_batch(self, batch):
        """Use multi-row INSERT for batch insertion (DuckDB optimized)."""
        if not batch:
            return

        columns = list(batch[0].keys())
        column_names = ", ".join([f'"{col}"' for col in columns])

        # Build VALUES clause with placeholders
        placeholders = ", ".join(["?" for _ in columns])
        sql = f"INSERT INTO {self.table} ({column_names}) VALUES ({placeholders})"

        # Prepare values
        values = [[row.get(col) for col in columns] for row in batch]

        # Use executemany for batch insertion
        self.conn.executemany(sql, values)

    def _insert_with_upsert(self, batch):
        """Use INSERT ... ON CONFLICT for upsert operations (DuckDB)."""
        if not batch:
            return

        if not self.upsert_key:
            raise ValueError("upsert_key must be specified for upsert mode")

        columns = list(batch[0].keys())

        # Determine conflict keys
        if isinstance(self.upsert_key, str):
            conflict_keys = [self.upsert_key]
        else:
            conflict_keys = self.upsert_key

        # Build UPDATE clause for ON CONFLICT
        update_columns = [col for col in columns if col not in conflict_keys]
        if not update_columns:
            # If only conflict keys exist, use DO NOTHING
            update_clause = "DO NOTHING"
        else:
            update_clause = ", ".join([f'"{col}" = EXCLUDED."{col}"' for col in update_columns])

        # Build conflict target
        conflict_target = ", ".join([f'"{key}"' for key in conflict_keys])

        column_names = ", ".join([f'"{col}"' for col in columns])
        placeholders = ", ".join(["?" for _ in columns])

        if update_clause == "DO NOTHING":
            sql = f"""
                INSERT INTO {self.table} ({column_names})
                VALUES ({placeholders})
                ON CONFLICT ({conflict_target}) DO NOTHING
            """
        else:
            sql = f"""
                INSERT INTO {self.table} ({column_names})
                VALUES ({placeholders})
                ON CONFLICT ({conflict_target}) DO UPDATE SET {update_clause}
            """

        values = [[row.get(col) for col in columns] for row in batch]

        # Use executemany for batch upsert
        self.conn.executemany(sql, values)

    def _use_appender(self, batch):
        """Use DuckDB Appender API for streaming insertion."""
        if not batch:
            return

        # Get column names
        if self._table_columns:
            columns = self._table_columns
        else:
            columns = list(batch[0].keys())

        # Create appender if available
        if self._appender is None and hasattr(self.conn, "appender"):
            self._appender = self.conn.appender(self.table)

        if self._appender is not None:
            # Append each row
            for row in batch:
                values = [row.get(col) for col in columns]
                self._appender.append_row(values)
            return

        # Fallback: use DuckDB append(DataFrame) if available, otherwise batch insert
        try:
            import pandas as pd

            df = pd.DataFrame(batch, columns=columns)
            self.conn.append(self.table, df, by_name=True)
        except Exception:
            self._insert_batch(batch)

    def ingest(self, batch):
        """Ingest batch of records to DuckDB with retry logic."""
        if not batch:
            return

        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                # Create table if needed
                if self.create_table and not self._schema_created:
                    schema = self._infer_schema(batch)
                    self._create_table(schema)
                elif not self.create_table:
                    # Validate schema matches
                    if not self._validate_schema(batch):
                        raise ValueError(f"Schema mismatch for table {self.table}")

                # Ingest based on mode and method
                if self.use_appender:
                    self._use_appender(batch)
                elif self.mode == "upsert":
                    self._insert_with_upsert(batch)
                else:
                    # Use batch insert for best performance (append or replace)
                    # Truncate on first batch for replace mode
                    if self.mode == "replace":
                        if self._replace_per_call or not self._first_batch_processed:
                            self.conn.execute(f"DELETE FROM {self.table}")
                            if not self._replace_per_call:
                                self._first_batch_processed = True
                    self._insert_batch(batch)

                return

            except Exception as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"DuckDB ingestion failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"DuckDB ingestion failed after {MAX_RETRIES} attempts: {e}")
                    raise

        if last_exception:
            raise last_exception

    def close(self):
        """Close DuckDB connection and appender."""
        if self._appender:
            try:
                self._appender.close()
                self._appender = None
            except Exception:
                # Best effort: never fail the command because of this step.
                logging.getLogger(__name__).debug(
                    "ignoring error while closing DuckDB resources", exc_info=True
                )

        if hasattr(self, "conn") and self.conn:
            try:
                self.conn.close()
            except Exception:
                # Best effort: never fail the command because of this step.
                logging.getLogger(__name__).debug(
                    "ignoring error while closing DuckDB resources", exc_info=True
                )
