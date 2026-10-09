"""Ingest orchestrator dispatching to database-specific backends."""

import logging
import time
from typing import Any

import duckdb

from ...common.command_utils import get_iterable_options, iter_command_rows
from ...common.progress import progress
from ...common.s3_iterable import open_iterable_with_s3
from .base import (
    DEFAULT_BATCH_SIZE,
    DUCKABLE_CODECS,
    DUCKABLE_FILE_TYPES,
    MYSQL_CONNECTION_POOL_SIZE,
    POSTGRES_CONNECTION_POOL_SIZE,
)
from .duckdb_backend import DuckDBIngester
from .elastic import ElasticIngester
from .mongo import MongoIngester
from .mysql_backend import MySQLIngester
from .postgres import PostgresIngester
from .sqlite_backend import SQLiteIngester

logger = logging.getLogger(__name__)


class Ingester:
    """Main data ingestion handler.

    Coordinates file reading, batching, and database-specific ingestion.
    Supports multiple files and provides progress tracking and error handling.

    Args:
        batch_size: Number of records per batch (default: 1000)
    """

    def __init__(self, batch_size=DEFAULT_BATCH_SIZE):
        self.batch_size = batch_size

    def ingest(self, fromfiles, uri, db, table, options=None):
        """Ingest data from multiple files to a database.

        Args:
            fromfiles: List of file paths or glob patterns
            uri: Database connection URI
            db: Database name
            table: Collection or table name
            options: Dictionary of ingestion options (dbtype, drop, timeout, etc.)
        """
        if options is None:
            options = {}
        for filename in fromfiles:
            self.ingest_single(filename, uri, db, table, options)

    def ingest_single(self, fromfile, uri, db, table, options=None):
        """Loads single file data contents to a database.

        Processes a single file, reading records in batches and ingesting them
        to the specified database. Provides progress tracking, error handling,
        and summary statistics.

        Args:
            fromfile: Path to input file
            uri: Database connection URI
            db: Database name
            table: Collection or table name
            options: Dictionary of ingestion options:
                - dbtype: Database type ('mongodb', 'elasticsearch', 'elastic', 'postgresql', 'postgres', 'duckdb', 'mysql', 'sqlite')
                - drop: Drop collection/table before ingestion (bool)
                - timeout: Connection timeout in seconds (int, positive values)
                - skip: Number of records to skip (int)
                - totals: Show total record counts (bool)
                - api_key: API key for authentication (str, Elasticsearch)
                - doc_id: Document ID field name (str, Elasticsearch, default: 'id')

        Raises:
            ValueError: If unsupported database type is specified
            ConnectionError: If database connection fails
        """
        if options is None:
            options = {}
        dbtype = options["dbtype"]
        processor: Any = None
        totals = -1
        skip = options.get("skip")
        use_totals = options.get("totals", False)
        do_drop = options.get("drop", False)  # Fixed typo: was 'dro[]'
        timeout = options.get("timeout")

        # Convert timeout: negative values mean use default, positive values are seconds
        if timeout and timeout > 0:
            timeout_seconds = timeout
        else:
            timeout_seconds = None

        from ...common.errors import (
            DatabaseError,
            FileNotFoundError,
            PermissionError,
            find_similar_files,
        )
        from ...common.path_utils import validate_file_path

        # Validate input file exists and is readable
        try:
            validate_file_path(fromfile, check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(fromfile)
            raise FileNotFoundError(fromfile, suggestions) from e
        except PermissionError as e:
            raise PermissionError(fromfile, operation="read") from e

        logger.info(f"Ingesting {fromfile} to {uri} with db {db} table {table}")

        # Calculate total records for progress bar
        if use_totals:
            parts = fromfile.rsplit(".", 2)
            if len(parts) == 2:
                if parts[-1].lower() in DUCKABLE_FILE_TYPES:
                    try:
                        totals = duckdb.sql(f"select count(*) from '{fromfile}'").fetchone()[0]
                    except Exception as e:
                        logger.warning(f"Could not count records in {fromfile}: {e}")
            elif len(parts) == 3:
                if (
                    parts[-2].lower() in DUCKABLE_FILE_TYPES
                    and parts[-1].lower() in DUCKABLE_CODECS
                ):
                    try:
                        totals = duckdb.sql(f"select count(*) from '{fromfile}'").fetchone()[0]
                    except Exception as e:
                        logger.warning(f"Could not count records in {fromfile}: {e}")

        # Initialize processor with timeout support
        if dbtype == "mongodb":
            processor = MongoIngester(uri, db, table, do_drop=do_drop, timeout=timeout_seconds)
        elif dbtype in {"elastic", "elasticsearch"}:
            api_key = options.get("api_key")
            id_key = options.get("doc_id") or "id"
            processor = ElasticIngester(
                uri=uri,
                api_key=api_key,
                search_index=table,
                document_id=id_key,
                timeout=timeout_seconds or 60,
                verify_certs=not options.get("insecure", False),
                ca_certs=options.get("ca_cert"),
                pipeline=options.get("es_pipeline"),
            )
        elif dbtype in {"postgresql", "postgres"}:
            mode = options.get("mode", "append")
            create_table = options.get("create_table", False)
            upsert_key = options.get("upsert_key")
            pool_size = options.get("pool_size", POSTGRES_CONNECTION_POOL_SIZE)
            # For replace mode, set drop equivalent
            if mode == "replace" and not create_table:
                do_drop = True  # Will be handled by truncate in first batch
            processor = PostgresIngester(
                uri=uri,
                db=db,
                table=table,
                mode=mode,
                create_table=create_table,
                upsert_key=upsert_key,
                timeout=timeout_seconds,
                pool_size=pool_size,
            )
        elif dbtype == "duckdb":
            mode = options.get("mode", "append")
            create_table = options.get("create_table", False)
            upsert_key = options.get("upsert_key")
            use_appender = options.get("use_appender", False)
            processor = DuckDBIngester(
                uri=uri,
                table=table,
                mode=mode,
                create_table=create_table,
                upsert_key=upsert_key,
                use_appender=use_appender,
            )
        elif dbtype == "mysql":
            mode = options.get("mode", "append")
            create_table = options.get("create_table", False)
            upsert_key = options.get("upsert_key")
            pool_size = options.get("pool_size", MYSQL_CONNECTION_POOL_SIZE)
            processor = MySQLIngester(
                uri=uri,
                db=db,
                table=table,
                mode=mode,
                create_table=create_table,
                upsert_key=upsert_key,
                timeout=timeout_seconds,
                pool_size=pool_size,
            )
        elif dbtype == "sqlite":
            mode = options.get("mode", "append")
            create_table = options.get("create_table", False)
            upsert_key = options.get("upsert_key")
            processor = SQLiteIngester(
                uri=uri, table=table, mode=mode, create_table=create_table, upsert_key=upsert_key
            )
        elif dbtype == "clickhouse":
            from .clickhouse_backend import ClickHouseIngester

            processor = ClickHouseIngester(
                uri=uri,
                table=table,
                mode=options.get("mode", "append"),
                create_table=options.get("create_table", False),
                table_engine=options.get("table_engine"),
            )
        elif dbtype == "mssql":
            from .mssql_backend import MSSQLIngester

            processor = MSSQLIngester(
                uri=uri,
                table=table,
                mode=options.get("mode", "append"),
                create_table=options.get("create_table", False),
                upsert_key=options.get("upsert_key"),
            )
        else:
            from ...common.errors import ValidationError

            supported_types = [
                "mongodb",
                "elasticsearch",
                "elastic",
                "postgresql",
                "postgres",
                "duckdb",
                "mysql",
                "sqlite",
                "clickhouse",
                "mssql",
            ]
            raise ValidationError(
                f"Unsupported database type: '{dbtype}'",
                field="dbtype",
                suggestions=supported_types,
            )

        if hasattr(processor, "_replace_per_call"):
            processor._replace_per_call = False
            processor._first_batch_processed = False

        # Validate connection before starting
        try:
            if dbtype == "mongodb":
                # Test MongoDB connection
                processor.client.server_info()
            elif dbtype in {"elastic", "elasticsearch"}:
                # Test Elasticsearch connection
                processor.client.info()
            elif dbtype in {"postgresql", "postgres"}:
                # Test PostgreSQL connection
                conn = processor._get_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                finally:
                    processor._put_connection(conn)
            elif dbtype == "duckdb":
                # Test DuckDB connection (simple query)
                processor.conn.execute("SELECT 1").fetchone()
            elif dbtype == "mysql":
                # Test MySQL connection
                conn = processor._get_connection()
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                        cur.fetchone()
                finally:
                    conn.close()
            elif dbtype == "sqlite":
                # Test SQLite connection (simple query)
                processor.conn.execute("SELECT 1").fetchone()
            elif dbtype in ("clickhouse", "mssql"):
                processor.check_connection()
        except Exception as e:
            from ...common.errors import DatabaseError

            raise DatabaseError(
                f"Failed to connect to database: {e}", db_type=dbtype, connection_uri=uri
            ) from e

        iterableargs = get_iterable_options(options)
        iterable_context = open_iterable_with_s3(fromfile, mode="r", iterableargs=iterableargs)
        it_in = iterable_context.__enter__()

        # Statistics tracking
        start_time = time.time()
        total_rows = 0
        successful_rows = 0
        failed_rows = 0
        batch_count = 0
        errors = []

        try:
            logger.info(f"Ingesting data: filename {fromfile}, uri: {uri}, db {db}, table {table}")
            n = 0
            batch = []

            # Enhanced progress bar with throughput
            with progress(
                iter_command_rows(it_in, options),
                total=totals,
                desc=f"Ingesting to {dbtype}",
                unit="rows",
            ) as pbar:
                for row in pbar:
                    n += 1
                    if skip is not None and skip > 0:
                        if n < skip:
                            continue

                    batch.append(row)
                    total_rows += 1

                    if len(batch) >= self.batch_size:
                        batch_count += 1
                        try:
                            processor.ingest(batch)
                            successful_rows += len(batch)
                            # Update progress bar with throughput
                            elapsed = time.time() - start_time
                            if elapsed > 0:
                                throughput = successful_rows / elapsed
                                pbar.set_postfix({"throughput": f"{throughput:.0f} rows/s"})
                        except Exception as e:
                            failed_rows += len(batch)
                            error_msg = f"Batch {batch_count} failed: {e}"
                            errors.append(error_msg)
                            logger.error(error_msg)
                            # Continue with next batch
                        batch = []

                # Process remaining batch
                if len(batch) > 0:
                    batch_count += 1
                    try:
                        processor.ingest(batch)
                        successful_rows += len(batch)
                    except Exception as e:
                        failed_rows += len(batch)
                        error_msg = f"Final batch {batch_count} failed: {e}"
                        errors.append(error_msg)
                        logger.error(error_msg)

        finally:
            it_in.close()
            iterable_context.__exit__(None, None, None)

            # Close database connections if needed
            if dbtype in (
                "postgresql",
                "postgres",
                "duckdb",
                "mysql",
                "sqlite",
                "clickhouse",
                "mssql",
            ) and hasattr(processor, "close"):
                try:
                    processor.close()
                except Exception as e:
                    logger.warning(f"Error closing database connection: {e}")

            # Print summary statistics
            elapsed_time = time.time() - start_time
            print("\nIngestion Summary:")
            print(f"  Total rows processed: {total_rows}")
            print(f"  Successful rows: {successful_rows}")
            print(f"  Failed rows: {failed_rows}")
            print(f"  Batches processed: {batch_count}")
            print(f"  Time elapsed: {elapsed_time:.2f} seconds")
            if elapsed_time > 0:
                print(f"  Average throughput: {successful_rows / elapsed_time:.0f} rows/second")
            if errors:
                print(f"  Errors encountered: {len(errors)}")
                if logging.getLogger().level <= logging.DEBUG:
                    for error in errors:
                        print(f"    - {error}")

        if failed_rows:
            from ...common.errors import DatabaseError

            raise DatabaseError(
                f"{failed_rows} of {total_rows} rows were not loaded: {errors[0]}",
                db_type=dbtype,
            )
