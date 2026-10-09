"""PostgreSQL ingester backend."""

import csv
import io
import logging
import time

try:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import execute_values

    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    psycopg2 = None
    pool = None
    execute_values = None

from .base import (
    INITIAL_RETRY_DELAY,
    MAX_RETRIES,
    POSTGRES_CONNECTION_POOL_SIZE,
    BasicIngester,
)

logger = logging.getLogger(__name__)


class PostgresIngester(BasicIngester):
    """PostgreSQL data ingester.

    Handles bulk ingestion of records to PostgreSQL with COPY FROM for maximum
    performance, upsert support, and schema management. Uses connection pooling
    for efficient connection management.

    Args:
        uri: PostgreSQL connection URI (postgresql://user:pass@host:port/db)
        db: Database name (overrides URI database if provided)
        table: Table name
        mode: Ingestion mode: 'append', 'replace', or 'upsert' (default: 'append')
        create_table: If True, auto-create table from data schema (default: False)
        upsert_key: Field name(s) to use for conflict resolution in upsert mode
        timeout: Connection timeout in seconds (None uses default)
        pool_size: Connection pool size (default: 5)
    """

    def __init__(
        self,
        uri,
        db,
        table,
        mode="append",
        create_table=False,
        upsert_key=None,
        timeout=None,
        pool_size=POSTGRES_CONNECTION_POOL_SIZE,
    ):
        if not PSYCOPG2_AVAILABLE:
            raise ImportError(
                "psycopg2 is required for PostgreSQL support. "
                "Install it with: pip install psycopg2-binary"
            )

        self.uri = uri
        self.db = db
        self.table = table
        self.mode = mode
        self.create_table = create_table
        self.upsert_key = upsert_key
        self.timeout = timeout
        self.pool_size = pool_size

        # Parse connection parameters from URI
        self.conn_params = self._parse_uri(uri)

        # Use db parameter if provided, otherwise use from URI
        database = db if db else self.conn_params.get("database")
        if not database:
            raise ValueError("Database name must be provided either in URI or as 'db' parameter")

        # Create connection pool
        try:
            self.pool = pool.ThreadedConnectionPool(
                1,
                pool_size,
                host=self.conn_params.get("host", "localhost"),
                port=self.conn_params.get("port", 5432),
                database=database,
                user=self.conn_params.get("user"),
                password=self.conn_params.get("password"),
                connect_timeout=timeout or 30,
            )
        except Exception as e:
            raise ConnectionError(f"Failed to create PostgreSQL connection pool: {e}") from e

        self._schema_created = False
        self._table_columns = None
        self._first_batch_processed = False

    def _parse_uri(self, uri):
        """Parse a PostgreSQL connection URI into driver connection parameters."""
        from ...common.db_connection import parse_server_uri

        return parse_server_uri(uri, ("postgresql", "postgres"), default_port=5432)

    def _get_connection(self):
        """Get a connection from the pool."""
        return self.pool.getconn()

    def _put_connection(self, conn):
        """Return a connection to the pool."""
        self.pool.putconn(conn)

    def _infer_schema(self, batch):
        """Infer PostgreSQL schema from a sample batch of records.

        Analyzes multiple records to determine the best type for each column.
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
                pg_type = "TEXT"  # Default if all nulls
            elif all(isinstance(v, bool) for v in non_null_values):
                pg_type = "BOOLEAN"
            elif all(isinstance(v, int) for v in non_null_values):
                pg_type = "BIGINT"
            elif all(isinstance(v, float) for v in non_null_values):
                pg_type = "DOUBLE PRECISION"
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
                    pg_type = "TIMESTAMP"
                elif date_count > 0:
                    pg_type = "DATE"
                else:
                    # Use VARCHAR with reasonable length estimate
                    max_len = max(len(str(v)) for v in non_null_values[:100])
                    if max_len > 255:
                        pg_type = "TEXT"
                    else:
                        pg_type = f"VARCHAR({min(max_len * 2, 1000)})"  # 2x buffer, max 1000
            else:
                # Mixed types, default to TEXT
                pg_type = "TEXT"

            schema.append((key, pg_type))

        return schema

    def _create_table(self, schema, conn):
        """Create table from inferred schema."""
        # Check if table exists
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                )
            """,
                (self.table,),
            )
            table_exists = cur.fetchone()[0]

        if table_exists:
            if self.mode == "replace":
                # Drop and recreate
                with conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {self.table}")
                    conn.commit()
            else:
                # Table exists and not replacing, just validate schema matches
                logger.info(f"Table {self.table} already exists, skipping creation")
                self._schema_created = True
                self._table_columns = [col for col, _ in schema]
                return

        # Build CREATE TABLE statement
        columns = ", ".join([f'"{col}" {pg_type}' for col, pg_type in schema])
        create_sql = f"CREATE TABLE IF NOT EXISTS {self.table} ({columns})"

        with conn.cursor() as cur:
            cur.execute(create_sql)
            conn.commit()

        self._schema_created = True
        self._table_columns = [col for col, _ in schema]
        logger.info(
            f"Created table {self.table} with schema: {', '.join([f'{col} {pg_type}' for col, pg_type in schema])}"
        )

    def _validate_schema(self, batch, conn):
        """Validate that batch schema matches table schema.

        Returns True if schema matches, False otherwise.
        Logs warnings for mismatches but allows continuation.
        """
        if not batch:
            return True

        # Get table columns
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s
                ORDER BY ordinal_position
            """,
                (self.table,),
            )
            table_schema = {row[0]: row[1] for row in cur.fetchall()}

        if not table_schema:
            logger.warning(f"Table {self.table} does not exist or has no columns")
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

    def _copy_from_csv(self, batch, conn):
        """Use COPY FROM for fast bulk loading."""
        if not batch:
            return

        # Get column names
        if self._table_columns:
            columns = self._table_columns
        else:
            columns = list(batch[0].keys())

        # Convert batch to CSV format in memory
        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        for row in batch:
            # Handle None values as empty strings for CSV
            values = []
            for col in columns:
                val = row.get(col)
                if val is None:
                    values.append("")
                else:
                    values.append(str(val))
            writer.writerow(values)

        output.seek(0)

        # Use COPY FROM for maximum performance
        with conn.cursor() as cur:
            quoted_columns = ", ".join([f'"{col}"' for col in columns])
            cur.copy_expert(
                f"COPY {self.table} ({quoted_columns}) FROM STDIN WITH (FORMAT CSV)",
                output,
            )
            conn.commit()

    def _insert_with_upsert(self, batch, conn):
        """Use INSERT ... ON CONFLICT for upsert operations."""
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

        # Build UPDATE clause for ON CONFLICT (update all columns except conflict keys)
        update_columns = [col for col in columns if col not in conflict_keys]
        if not update_columns:
            # If only conflict keys exist, use DO NOTHING
            update_clause = "DO NOTHING"
        else:
            update_clause = ", ".join([f'"{col}" = EXCLUDED."{col}"' for col in update_columns])

        # Build conflict target
        conflict_target = ", ".join([f'"{key}"' for key in conflict_keys])

        # Check if table has unique constraint or primary key on conflict keys
        # For now, assume conflict keys form a unique constraint
        column_names = ", ".join([f'"{col}"' for col in columns])
        placeholders = ", ".join(["%s"] * len(columns))

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

        with conn.cursor() as cur:
            execute_values(cur, sql, values, template=None, page_size=100)
            conn.commit()

    def _insert_batch(self, batch, conn):
        """Use multi-row INSERT for batch insertion."""
        if not batch:
            return

        columns = list(batch[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        column_names = ", ".join([f'"{col}"' for col in columns])

        sql = f"INSERT INTO {self.table} ({column_names}) VALUES ({placeholders})"
        values = [[row.get(col) for col in columns] for row in batch]

        with conn.cursor() as cur:
            execute_values(cur, sql, values, template=None, page_size=100)
            conn.commit()

    def ingest(self, batch):
        """Ingest batch of records to PostgreSQL with retry logic."""
        if not batch:
            return

        conn = None
        last_exception = None

        for attempt in range(MAX_RETRIES):
            try:
                conn = self._get_connection()

                # Create table if needed
                if self.create_table and not self._schema_created:
                    schema = self._infer_schema(batch)
                    self._create_table(schema, conn)
                elif not self.create_table:
                    # Validate schema matches
                    if not self._validate_schema(batch, conn):
                        raise ValueError(f"Schema mismatch for table {self.table}")

                # Ingest based on mode
                if self.mode == "upsert":
                    self._insert_with_upsert(batch, conn)
                else:
                    # Use COPY FROM for best performance (append or replace)
                    # Truncate on first batch for replace mode
                    if self.mode == "replace" and not self._first_batch_processed:
                        with conn.cursor() as cur:
                            cur.execute(f"TRUNCATE TABLE {self.table}")
                            conn.commit()
                        self._first_batch_processed = True
                    self._copy_from_csv(batch, conn)

                self._put_connection(conn)
                return

            except Exception as e:
                if conn:
                    try:
                        conn.rollback()
                        self._put_connection(conn)
                    except Exception:
                        # Best effort: never fail the command because of this step.
                        logging.getLogger(__name__).debug(
                            "ignoring rollback error before retry", exc_info=True
                        )

                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"PostgreSQL ingestion failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"PostgreSQL ingestion failed after {MAX_RETRIES} attempts: {e}")
                    raise

        if last_exception:
            raise last_exception

    def close(self):
        """Close connection pool."""
        if hasattr(self, "pool") and self.pool:
            self.pool.closeall()
