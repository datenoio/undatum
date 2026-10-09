"""CLI commands for database query and load."""

import logging
import sys
from typing import Annotated

import typer

from ..common.errors import UndatumError
from .common import enable_verbose

logger = logging.getLogger(__name__)

db_app = typer.Typer(help="Database query and load commands.")


@db_app.command(name="query")
def db_query(
    query: Annotated[str, typer.Argument(help="SQL query to execute.")],
    db: Annotated[
        str,
        typer.Option(help="Database connection URI (e.g., postgresql://user:pass@host:port/db)."),
    ],
    output: Annotated[
        str, typer.Option(help="Output file path. If not specified, prints to stdout.")
    ] = None,
    output_format: Annotated[
        str, typer.Option(help="Output format: 'jsonl' (default), 'csv', or 'parquet'.")
    ] = "jsonl",
    query_file: Annotated[
        str, typer.Option(help="Path to SQL query file (alternative to query argument).")
    ] = None,
    batch_size: Annotated[
        int, typer.Option(help="Batch size for streaming results (default: 10000).")
    ] = 10000,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Execute SQL query against database and output results.

    Natively supports PostgreSQL, MySQL/MariaDB, and SQLite. Additional engines
    are served through iterabledata's read-only drivers: MS SQL Server (mssql://,
    sqlserver://), ClickHouse (clickhouse://), MongoDB (mongodb://), and
    Elasticsearch/OpenSearch (elasticsearch://, opensearch://).
    Results are streamed for efficient memory usage with large result sets.

    Examples:
        # Query PostgreSQL
        undatum db query "SELECT * FROM users LIMIT 100" --db postgresql://user:pass@host/db

        # Query MySQL and save to file
        undatum db query "SELECT name, email FROM customers" --db mysql://user:pass@host:3306/mydb --output results.jsonl

        # Query SQLite and output CSV
        undatum db query "SELECT * FROM data" --db sqlite:///path/to/db.db --output-format csv

        # Query ClickHouse / MS SQL Server (via iterabledata drivers)
        undatum db query "SELECT * FROM events LIMIT 100" --db clickhouse://user:pass@host:9000/db

        # Read a MongoDB collection (collection given in the URI, no SQL needed)
        undatum db query "" --db "mongodb://host:27017/mydb?collection=users&limit=100"

        # Query from file
        undatum db query --query-file query.sql --db postgresql://user:pass@host/db
    """
    from ..cmds.db_query import DatabaseQueryExecutor

    if verbose:
        enable_verbose()

    # Read query from file if provided
    if query_file:
        try:
            with open(query_file, encoding="utf-8") as f:
                query = f.read()
        except Exception as e:
            logger.error(f"Failed to read query file: {e}")
            sys.exit(1)

    executor = DatabaseQueryExecutor()
    try:
        executor.query(query, db, output, output_format, batch_size)
    except (UndatumError, ImportError):
        raise  # reported by the entry point with the documented exit code
    except Exception as e:
        logger.error(f"Query execution failed: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@db_app.command()
def load(
    input_file: Annotated[str, typer.Argument(help="Path to input file to load.")],
    db: Annotated[
        str,
        typer.Option(help="Database connection URI (e.g., postgresql://user:pass@host:port/db)."),
    ],
    table: Annotated[str, typer.Option(help="Target table name.")],
    mode: Annotated[
        str, typer.Option(help="Load mode: 'append' (default), 'replace', or 'upsert'.")
    ] = "append",
    create_table: Annotated[
        bool, typer.Option(help="Auto-create table from data schema if it doesn't exist.")
    ] = False,
    upsert_key: Annotated[
        str, typer.Option(help="Key field(s) for upsert mode (comma-separated).")
    ] = None,
    source_table: Annotated[
        str | None,
        typer.Option(
            "--source-table",
            "--sheet",
            help="Source table or sheet name for multi-table files (Excel, SQLite, lakehouse).",
        ),
    ] = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: Annotated[
        bool,
        typer.Option(
            "--trust",
            help="Acknowledge pickle deserialization risk when reading pickle sources.",
        ),
    ] = False,
    on_error: Annotated[
        str | None,
        typer.Option(
            "--on-error",
            help="Parse-error policy: raise (default), skip, or warn.",
        ),
    ] = None,
    error_log: Annotated[
        str | None,
        typer.Option(
            "--error-log",
            help="Append parse errors as JSONL (use with --on-error skip or warn).",
        ),
    ] = None,
    quotechar: Annotated[
        str | None,
        typer.Option(
            "--quotechar",
            help="CSV quote character (iterabledata default '\"' when omitted).",
        ),
    ] = None,
    flatten_nested: Annotated[
        bool,
        typer.Option(
            "--flatten-nested",
            help="Unfold nested dict / array-of-dict fields into dotted paths (e.g. city.lat).",
        ),
    ] = False,
    max_nested_depth: Annotated[
        int | None,
        typer.Option(
            "--max-nested-depth",
            help="With --flatten-nested, maximum nest depth to unfold (engine default 5).",
        ),
    ] = None,
    keep_nested_parents: Annotated[
        bool,
        typer.Option(
            "--keep-nested-parents/--no-keep-nested-parents",
            help="With --flatten-nested, keep parent dict/array fields alongside dotted children.",
        ),
    ] = True,
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            envvar="ELASTIC_API_KEY",
            help="Elasticsearch/OpenSearch API key (or set ELASTIC_API_KEY).",
        ),
    ] = None,
    doc_id: Annotated[
        str | None,
        typer.Option("--doc-id", help="Field used as the document ID (Elasticsearch)."),
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
    table_engine: Annotated[
        str | None,
        typer.Option(
            "--table-engine",
            help="ClickHouse ENGINE for --create-table (default: MergeTree ORDER BY tuple()).",
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Load data from file to database table.

    Supports PostgreSQL, MySQL/MariaDB, SQLite, DuckDB, ClickHouse (``clickhouse://host:8123/db``),
    SQL Server (``mssql://user:pass@host:1433/db``), MongoDB (``mongodb://host/db``, the
    collection is ``--table``) and Elasticsearch/OpenSearch (``elasticsearch://host:9200``
    over HTTPS, ``elasticsearch+http://`` for plain HTTP; the index is ``--table``).

    Examples:
        # Load data to PostgreSQL (append mode)
        undatum db load data.parquet --db postgresql://user:pass@host/db --table users

        # Load with replace mode
        undatum db load data.csv --db mysql://user:pass@host:3306/mydb --table customers --mode replace

        # Load with upsert
        undatum db load data.jsonl --db postgresql://user:pass@host/db --table orders --mode upsert --upsert-key id

        # Auto-create table
        undatum db load data.parquet --db sqlite:///db.db --table new_table --create-table

        # MongoDB collection and Elasticsearch index
        undatum db load data.jsonl --db mongodb://localhost:27017/shop --table orders
        undatum db load data.jsonl --db elasticsearch://localhost:9200 --table logs --api-key KEY
        undatum db load nested.jsonl --db sqlite:///db.db --table cities --create-table --flatten-nested
    """
    from ..cmds.db_load import DatabaseLoader

    if verbose:
        enable_verbose()

    loader = DatabaseLoader()
    try:
        loader.load(
            input_file,
            db,
            table,
            mode,
            create_table,
            upsert_key,
            source_table=source_table,
            start_page=start_page,
            trust=trust,
            on_error=on_error,
            error_log=error_log,
            quotechar=quotechar,
            flatten_nested=flatten_nested,
            max_nested_depth=max_nested_depth,
            keep_nested_parents=keep_nested_parents,
            api_key=api_key,
            doc_id=doc_id,
            insecure=insecure,
            ca_cert=ca_cert,
            es_pipeline=es_pipeline,
            table_engine=table_engine,
        )
    except (UndatumError, ImportError):
        raise  # reported by the entry point with the documented exit code
    except Exception as e:
        logger.error(f"Load operation failed: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@db_app.command()
def dump(
    db: Annotated[
        str,
        typer.Option(help="Database connection URI (e.g., postgresql://user:pass@host:port/db)."),
    ],
    output: Annotated[str, typer.Option(help="Output file path.")],
    table: Annotated[
        str, typer.Option(help="Table name to dump (use with --to / output format).")
    ] = None,
    query: Annotated[str, typer.Option(help="SQL query to dump (alternative to --table).")] = None,
    to_format: Annotated[
        str,
        typer.Option(
            "--to",
            help="Output format: 'parquet' (default), 'csv', or 'jsonl'.",
        ),
    ] = "parquet",
    batch_size: Annotated[
        int, typer.Option(help="Batch size for streaming results (default: 10000).")
    ] = 10000,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Dump a database table or query result to a file.

    Streams results for efficient memory usage. Prefer Parquet for large dumps.

    Examples:
        undatum db dump --db sqlite:///data.db --table users --output users.parquet

        undatum db dump --db postgresql://user:pass@host/db --query "SELECT * FROM events" \\
            --output events.csv --to csv
    """
    from ..cmds.db_dump import DatabaseDumper

    if verbose:
        enable_verbose()

    dumper = DatabaseDumper()
    try:
        dumper.dump(
            db, output, table=table, query=query, output_format=to_format, batch_size=batch_size
        )
    except (UndatumError, ImportError):
        raise  # reported by the entry point with the documented exit code
    except Exception as e:
        logger.error(f"Dump operation failed: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)
