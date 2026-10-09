"""SQL over files and loading into databases."""

import glob
from typing import Annotated

import typer

from ..common import enable_verbose
from ..options import (
    ErrorLogOpt,
    FlattenNestedOpt,
    KeepNestedParentsOpt,
    MaxNestedDepthOpt,
    OnErrorOpt,
    QuoteCharOpt,
    TrustOpt,
)
from ._app import data_app

DEFAULT_BATCH_SIZE = 1000


@data_app.command()
def ingest(
    input_file: Annotated[
        str, typer.Argument(help="Path to input file or glob pattern (e.g., 'data/*.jsonl').")
    ],
    uri: Annotated[
        str,
        typer.Argument(
            help="Database connection URI (e.g., 'mongodb://localhost:27017', 'postgresql://user:pass@host:5432/db', or 'https://elasticsearch:9200')."
        ),
    ],
    db: Annotated[str, typer.Argument(help="Database name.")],
    table: Annotated[str, typer.Argument(help="Collection or table name.")],
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    batch: Annotated[
        int,
        typer.Option(help="Batch size for ingestion (number of records per batch, default: 1000)."),
    ] = DEFAULT_BATCH_SIZE,
    dbtype: Annotated[
        str,
        typer.Option(
            help="Database type: 'mongodb' (default), 'postgresql', 'duckdb', 'mysql', 'sqlite', 'elasticsearch', or 'elastic'."
        ),
    ] = "mongodb",
    totals: Annotated[
        bool, typer.Option(help="Show total record counts during ingestion.")
    ] = False,
    drop: Annotated[
        bool, typer.Option(help="Drop existing collection/table before ingestion.")
    ] = False,
    timeout: Annotated[
        int | None,
        typer.Option(help="Connection timeout in seconds (driver default when omitted)."),
    ] = None,
    skip: Annotated[int, typer.Option(help="Number of records to skip at the beginning.")] = None,
    api_key: Annotated[
        str, typer.Option(help="API key for database authentication (Elasticsearch).")
    ] = None,
    insecure: Annotated[
        bool,
        typer.Option(
            "--insecure",
            help="Disable TLS certificate verification (Elasticsearch). Not recommended.",
        ),
    ] = False,
    ca_cert: Annotated[
        str | None,
        typer.Option("--ca-cert", help="CA bundle for TLS verification (Elasticsearch)."),
    ] = None,
    es_pipeline: Annotated[
        str | None,
        typer.Option("--es-pipeline", help="Elasticsearch ingest pipeline to apply."),
    ] = None,
    doc_id: Annotated[
        str, typer.Option(help="Field name to use as document ID (Elasticsearch, default: 'id').")
    ] = None,
    mode: Annotated[
        str,
        typer.Option(
            help="Ingestion mode for PostgreSQL/DuckDB/MySQL/SQLite: 'append' (default), 'replace', or 'upsert'."
        ),
    ] = "append",
    create_table: Annotated[
        bool,
        typer.Option(help="Auto-create table from data schema (PostgreSQL/DuckDB/MySQL/SQLite)."),
    ] = False,
    upsert_key: Annotated[
        str,
        typer.Option(
            help="Field name(s) to use for conflict resolution in upsert mode (PostgreSQL/DuckDB/MySQL/SQLite, comma-separated for multiple keys)."
        ),
    ] = None,
    use_appender: Annotated[
        bool,
        typer.Option(help="Use Appender API for DuckDB (streaming insertion, default: False)."),
    ] = False,
    source_table: Annotated[
        str | None,
        typer.Option(
            "--source-table",
            "--sheet",
            help="Source table or sheet name for multi-table files (Excel, SQLite, lakehouse).",
        ),
    ] = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    quotechar: QuoteCharOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Ingest data into a database.

    Supports MongoDB, PostgreSQL, DuckDB, MySQL, SQLite, and Elasticsearch databases.
    Reads data from files and inserts them into the specified database collection or table.

    For PostgreSQL:
    - Use COPY FROM for maximum performance (10-100x faster than INSERT)
    - Supports append, replace, and upsert modes
    - Can auto-create tables from data schema
    - Uses connection pooling for efficient connection management

    For DuckDB:
    - Fast bulk loading with optimized batch inserts
    - Supports append, replace, and upsert modes
    - Can auto-create tables from data schema
    - Appender API available for streaming insertion
    - Works with file-based or in-memory databases

    For MySQL:
    - Multi-row INSERT for efficient batch operations
    - Supports append, replace, and upsert modes
    - Can auto-create tables from data schema
    - Uses connection pooling for efficient connection management

    For SQLite:
    - Optimized batch inserts with PRAGMA optimizations
    - Supports append, replace, and upsert modes
    - Can auto-create tables from data schema
    - Works with file-based or in-memory databases
    """
    from ...cmds.ingester import Ingester

    if verbose:
        enable_verbose()

    # Parse upsert_key if provided (can be comma-separated)
    upsert_key_parsed = None
    if upsert_key:
        upsert_key_parsed = [k.strip() for k in upsert_key.split(",")]
        if len(upsert_key_parsed) == 1:
            upsert_key_parsed = upsert_key_parsed[0]

    options = {
        "dbtype": dbtype,
        "skip": skip,
        "drop": drop,
        "totals": totals,
        "doc_id": doc_id,
        "api_key": api_key,
        "timeout": timeout,
        "insecure": insecure,
        "ca_cert": ca_cert,
        "es_pipeline": es_pipeline,
        "mode": mode,
        "create_table": create_table,
        "upsert_key": upsert_key_parsed,
        "use_appender": use_appender,
        "table": source_table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "quotechar": quotechar,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Ingester(batch)
    files = glob.glob(input_file.strip("'"))
    acmd.ingest(files, uri, db, table, options)


@data_app.command()
def sql(
    query: Annotated[str, typer.Argument(help="DuckDB SQL query to execute.")],
    input_files: Annotated[
        list[str],
        typer.Argument(
            help="Input file(s). Each file is available as a view named after its file stem; "
            "a single file is also available as 'data'."
        ),
    ],
    output: Annotated[
        str | None, typer.Option(help="Output file path. Prints to stdout if omitted.")
    ] = None,
    format: Annotated[
        str, typer.Option(help="Output format: 'jsonl' (default), 'csv', or 'parquet'.")
    ] = "jsonl",
    duckdb_threads: Annotated[int | None, typer.Option(help="Number of DuckDB threads.")] = None,
    duckdb_memory: Annotated[
        str | None, typer.Option(help="DuckDB memory limit (e.g., '4GB', '512MB').")
    ] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Run an ad-hoc DuckDB SQL query over data files.

    Examples:
        # Query a single CSV (referenced as 'data')
        undatum sql "SELECT city, COUNT(*) AS n FROM data GROUP BY city" cities.csv

        # Join two files (views named after file stems)
        undatum sql "SELECT * FROM orders JOIN users USING (user_id)" orders.csv users.parquet

        # Save result as parquet
        undatum sql "SELECT * FROM data WHERE amount > 100" sales.jsonl --output big.parquet --format parquet
    """
    from ...cmds.sql import SqlExecutor

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "format": format,
        "duckdb_threads": duckdb_threads,
        "duckdb_memory": duckdb_memory,
    }
    SqlExecutor().query(query, input_files, options)
