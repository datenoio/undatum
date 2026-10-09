"""MySQL/MariaDB ingester backend."""

import logging
import time

try:
    import pymysql
    import pymysql.cursors

    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False
    pymysql = None

from .base import (
    INITIAL_RETRY_DELAY,
    MAX_RETRIES,
    MYSQL_CONNECTION_POOL_SIZE,
    BasicIngester,
)

logger = logging.getLogger(__name__)


class MySQLIngester(BasicIngester):
    """MySQL data ingester.

    Handles bulk ingestion of records to MySQL with LOAD DATA LOCAL INFILE for maximum
    performance, multi-row INSERT fallback, and upsert support. Uses connection pooling
    for efficient connection management.

    Args:
        uri: MySQL connection URI (mysql://user:pass@host:port/db)
        db: Database name
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
        pool_size=MYSQL_CONNECTION_POOL_SIZE,
    ):
        if not PYMYSQL_AVAILABLE:
            raise ImportError(
                "pymysql is required for MySQL support. Install it with: pip install pymysql"
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

        # Store connection parameters for creating connections
        self.conn_kwargs = {
            "host": self.conn_params.get("host", "localhost"),
            "port": self.conn_params.get("port", 3306),
            "user": self.conn_params.get("user"),
            "password": self.conn_params.get("password"),
            "database": db,
            "connect_timeout": timeout or 30,
            "local_infile": True,  # Enable LOAD DATA LOCAL INFILE
        }

        # Simple connection pool (reuse connections)
        self.pool_size = pool_size
        self._connections = []

        self._schema_created = False
        self._table_columns = None
        self._first_batch_processed = False

    def _parse_uri(self, uri):
        """Parse a MySQL connection URI into driver connection parameters."""
        from ...common.db_connection import parse_server_uri

        return parse_server_uri(uri, ("mysql", "mysql+pymysql"), default_port=3306)

    def _get_connection(self):
        """Get a connection (create new, PyMySQL doesn't have built-in pool)."""
        try:
            return pymysql.connect(**self.conn_kwargs)
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MySQL: {e}") from e

    def _infer_schema(self, batch):
        """Infer MySQL schema from a sample batch of records."""
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
                mysql_type = "TEXT"
            elif all(isinstance(v, bool) for v in non_null_values):
                mysql_type = "BOOLEAN"
            elif all(isinstance(v, int) for v in non_null_values):
                mysql_type = "BIGINT"
            elif all(isinstance(v, float) for v in non_null_values):
                mysql_type = "DOUBLE"
            elif all(isinstance(v, str) for v in non_null_values):
                max_len = max(len(str(v)) for v in non_null_values[:100])
                if max_len > 65535:
                    mysql_type = "LONGTEXT"
                elif max_len > 255:
                    mysql_type = "TEXT"
                else:
                    mysql_type = f"VARCHAR({min(max_len * 2, 255)})"
            else:
                mysql_type = "TEXT"

            schema.append((key, mysql_type))

        return schema

    def _create_table(self, schema, conn):
        """Create table from inferred schema."""
        with conn.cursor() as cur:
            cur.execute(f"SHOW TABLES LIKE '{self.table}'")
            table_exists = cur.fetchone() is not None

        if table_exists:
            if self.mode == "replace":
                with conn.cursor() as cur:
                    cur.execute(f"DROP TABLE IF EXISTS {self.table}")
                    conn.commit()
            else:
                logger.info(f"Table {self.table} already exists, skipping creation")
                self._schema_created = True
                self._table_columns = [col for col, _ in schema]
                return

        columns = ", ".join([f"`{col}` {mysql_type}" for col, mysql_type in schema])
        create_sql = f"CREATE TABLE IF NOT EXISTS {self.table} ({columns}) ENGINE=InnoDB"

        with conn.cursor() as cur:
            cur.execute(create_sql)
            conn.commit()

        self._schema_created = True
        self._table_columns = [col for col, _ in schema]
        logger.info(
            f"Created table {self.table} with schema: {', '.join([f'{col} {mysql_type}' for col, mysql_type in schema])}"
        )

    def _load_data_infile(self, batch, conn, temp_file):
        """Use LOAD DATA LOCAL INFILE for fast bulk loading."""
        if not batch:
            return

        columns = self._table_columns or list(batch[0].keys())
        column_names = ", ".join([f"`{col}`" for col in columns])

        load_sql = f"""
            LOAD DATA LOCAL INFILE '{temp_file}'
            INTO TABLE {self.table}
            FIELDS TERMINATED BY ',' ENCLOSED BY '"' ESCAPED BY '\\\\'
            LINES TERMINATED BY '\\n'
            ({column_names})
        """

        with conn.cursor() as cur:
            cur.execute(load_sql)
            conn.commit()

    def _insert_batch(self, batch, conn):
        """Use multi-row INSERT for batch insertion."""
        if not batch:
            return

        columns = list(batch[0].keys())
        column_names = ", ".join([f"`{col}`" for col in columns])
        placeholders = ", ".join(["%s"] * len(columns))

        sql = f"INSERT INTO {self.table} ({column_names}) VALUES ({placeholders})"
        values = [[row.get(col) for col in columns] for row in batch]

        with conn.cursor() as cur:
            cur.executemany(sql, values)
            conn.commit()

    def _insert_with_upsert(self, batch, conn):
        """Use INSERT ... ON DUPLICATE KEY UPDATE for upsert operations."""
        if not batch:
            return

        if not self.upsert_key:
            raise ValueError("upsert_key must be specified for upsert mode")

        columns = list(batch[0].keys())
        conflict_keys = [self.upsert_key] if isinstance(self.upsert_key, str) else self.upsert_key

        update_columns = [col for col in columns if col not in conflict_keys]
        if not update_columns:
            # Use INSERT IGNORE if no columns to update
            column_names = ", ".join([f"`{col}`" for col in columns])
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f"INSERT IGNORE INTO {self.table} ({column_names}) VALUES ({placeholders})"
        else:
            update_clause = ", ".join([f"`{col}` = VALUES(`{col}`)" for col in update_columns])
            column_names = ", ".join([f"`{col}`" for col in columns])
            placeholders = ", ".join(["%s"] * len(columns))
            sql = f"""
                INSERT INTO {self.table} ({column_names})
                VALUES ({placeholders})
                ON DUPLICATE KEY UPDATE {update_clause}
            """

        values = [[row.get(col) for col in columns] for row in batch]

        with conn.cursor() as cur:
            cur.executemany(sql, values)
            conn.commit()

    def ingest(self, batch):
        """Ingest batch of records to MySQL with retry logic."""
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

                # Ingest based on mode
                if self.mode == "upsert":
                    self._insert_with_upsert(batch, conn)
                else:
                    # Use multi-row INSERT (LOAD DATA requires file, which is complex)
                    if self.mode == "replace" and not self._first_batch_processed:
                        with conn.cursor() as cur:
                            cur.execute(f"TRUNCATE TABLE {self.table}")
                            conn.commit()
                        self._first_batch_processed = True
                    self._insert_batch(batch, conn)

                conn.close()
                return

            except Exception as e:
                if conn:
                    try:
                        conn.rollback()
                        conn.close()
                    except Exception:
                        # Best effort: never fail the command because of this step.
                        logging.getLogger(__name__).debug(
                            "ignoring rollback error before retry", exc_info=True
                        )

                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    delay = INITIAL_RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"MySQL ingestion failed (attempt {attempt + 1}/{MAX_RETRIES}), retrying in {delay}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"MySQL ingestion failed after {MAX_RETRIES} attempts: {e}")
                    raise

        if last_exception:
            raise last_exception

    def close(self):
        """Close any remaining connections."""
        # Connections are closed after each use, so nothing to do here
        pass
