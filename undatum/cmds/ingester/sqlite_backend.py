"""SQLite ingester backend."""

import logging
import sqlite3
import time

from .base import INITIAL_RETRY_DELAY, MAX_RETRIES, BasicIngester

logger = logging.getLogger(__name__)


class SQLiteIngester(BasicIngester):
    """SQLite data ingester.

    Handles bulk ingestion of records to SQLite with PRAGMA optimizations for maximum
    performance, executemany for batch inserts, and upsert support. SQLite is built-in
    to Python, so no external dependencies are required.

    Args:
        uri: SQLite connection URI (sqlite:///path/to/db.db or sqlite:///:memory:)
        table: Table name
        mode: Ingestion mode: 'append', 'replace', or 'upsert' (default: 'append')
        create_table: If True, auto-create table from data schema (default: False)
        upsert_key: Field name(s) to use for conflict resolution in upsert mode
    """

    def __init__(self, uri, table, mode="append", create_table=False, upsert_key=None):
        self.uri = uri
        self.table = table
        self.mode = mode
        self.create_table = create_table
        self.upsert_key = upsert_key

        # Parse connection string
        db_path = self._parse_uri(uri)

        # Connect to SQLite
        if db_path == ":memory:" or db_path is None:
            self.conn = sqlite3.connect(":memory:", check_same_thread=False)
            self.is_memory = True
        else:
            self.conn = sqlite3.connect(db_path, check_same_thread=False)
            self.is_memory = False

        # Apply PRAGMA optimizations for bulk loading
        self.conn.execute("PRAGMA synchronous = OFF")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA cache_size = 10000")
        self.conn.execute("PRAGMA temp_store = MEMORY")

        self._schema_created = False
        self._table_columns = None
        self._first_batch_processed = False
        self._original_pragmas = {}
        self._replace_per_call = True

    def _parse_uri(self, uri):
        """Parse SQLite connection URI into database path."""
        if uri.startswith("sqlite:///"):
            path = uri.replace("sqlite:///", "")
            if path == ":memory:":
                return ":memory:"
            return path
        elif uri.startswith("sqlite://"):
            path = uri.replace("sqlite://", "")
            if path == ":memory:":
                return ":memory:"
            return path
        else:
            return uri

    def _infer_schema(self, batch):
        """Infer SQLite schema from a sample batch of records."""
        if not batch:
            return []

        column_types = {}
        sample_size = min(len(batch), 100)

        for record in batch[:sample_size]:
            for key, value in record.items():
                if key not in column_types:
                    column_types[key] = []
                column_types[key].append(value)

        schema = []
        for key, values in column_types.items():
            non_null_values = [v for v in values if v is not None]

            if not non_null_values:
                sqlite_type = "TEXT"
            elif all(isinstance(v, bool) for v in non_null_values):
                sqlite_type = "INTEGER"  # SQLite uses INTEGER for booleans
            elif all(isinstance(v, int) for v in non_null_values):
                sqlite_type = "INTEGER"
            elif all(isinstance(v, float) for v in non_null_values):
                sqlite_type = "REAL"
            elif all(isinstance(v, str) for v in non_null_values):
                sqlite_type = "TEXT"
            else:
                sqlite_type = "TEXT"

            schema.append((key, sqlite_type))

        return schema

    def _create_table(self, schema):
        """Create table from inferred schema."""
        # Check if table exists
        try:
            result = self.conn.execute(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name='{self.table}'"
            ).fetchone()
            table_exists = result is not None
        except Exception:
            table_exists = False

        if table_exists:
            if self.mode == "replace":
                self.conn.execute(f"DROP TABLE IF EXISTS {self.table}")
            else:
                logger.info(f"Table {self.table} already exists, skipping creation")
                self._schema_created = True
                self._table_columns = [col for col, _ in schema]
                return

        column_defs = [f'"{col}" {sqlite_type}' for col, sqlite_type in schema]
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
        self.conn.commit()

        self._schema_created = True
        self._table_columns = [col for col, _ in schema]
        logger.info(
            f"Created table {self.table} with schema: {', '.join([f'{col} {sqlite_type}' for col, sqlite_type in schema])}"
        )

    def _insert_batch(self, batch):
        """Use executemany for batch insertion."""
        if not batch:
            return

        columns = list(batch[0].keys())
        column_names = ", ".join([f'"{col}"' for col in columns])
        placeholders = ", ".join(["?" for _ in columns])

        sql = f"INSERT INTO {self.table} ({column_names}) VALUES ({placeholders})"
        values = [tuple(row.get(col) for col in columns) for row in batch]

        self.conn.executemany(sql, values)
        self.conn.commit()

    def _insert_with_upsert(self, batch):
        """Use INSERT ... ON CONFLICT for upsert operations (SQLite 3.24+)."""
        if not batch:
            return

        if not self.upsert_key:
            raise ValueError("upsert_key must be specified for upsert mode")

        columns = list(batch[0].keys())
        conflict_keys = [self.upsert_key] if isinstance(self.upsert_key, str) else self.upsert_key

        update_columns = [col for col in columns if col not in conflict_keys]
        if not update_columns:
            # Use DO NOTHING if no columns to update
            column_names = ", ".join([f'"{col}"' for col in columns])
            placeholders = ", ".join(["?" for _ in columns])
            conflict_target = ", ".join([f'"{key}"' for key in conflict_keys])
            sql = f"""
                INSERT INTO {self.table} ({column_names})
                VALUES ({placeholders})
                ON CONFLICT ({conflict_target}) DO NOTHING
            """
        else:
            update_clause = ", ".join([f'"{col}" = EXCLUDED."{col}"' for col in update_columns])
            column_names = ", ".join([f'"{col}"' for col in columns])
            placeholders = ", ".join(["?" for _ in columns])
            conflict_target = ", ".join([f'"{key}"' for key in conflict_keys])
            sql = f"""
                INSERT INTO {self.table} ({column_names})
                VALUES ({placeholders})
                ON CONFLICT ({conflict_target}) DO UPDATE SET {update_clause}
            """

        values = [tuple(row.get(col) for col in columns) for row in batch]

        self.conn.executemany(sql, values)
        self.conn.commit()

    def ingest(self, batch):
        """Ingest batch of records to SQLite with retry logic."""
        if not batch:
            return

        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                # Create table if needed
                if self.create_table and not self._schema_created:
                    schema = self._infer_schema(batch)
                    self._create_table(schema)

                # Ingest based on mode
                if self.mode == "upsert":
                    self._insert_with_upsert(batch)
                else:
                    # Use batch insert
                    if self.mode == "replace":
                        if self._replace_per_call or not self._first_batch_processed:
                            self.conn.execute(f"DELETE FROM {self.table}")
                            self.conn.commit()
                            if not self._replace_per_call:
                                self._first_batch_processed = True
                    self._insert_batch(batch)

                return

            except Exception as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"SQLite ingestion failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"SQLite ingestion failed after {MAX_RETRIES} attempts: {e}")
                    raise

        if last_exception:
            raise last_exception

    def close(self):
        """Close SQLite connection."""
        if hasattr(self, "conn") and self.conn:
            try:
                self.conn.close()
            except Exception:
                # Best effort: never fail the command because of this step.
                logging.getLogger(__name__).debug(
                    "ignoring error while closing SQLite connection", exc_info=True
                )
