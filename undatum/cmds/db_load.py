"""Database load command for simplified data loading to databases."""

import logging
from urllib.parse import unquote, urlparse, urlunparse

from ..cmds.ingester import Ingester
from ..common.errors import DatabaseError, ValidationError

logger = logging.getLogger(__name__)

MONGODB_SCHEMES = ("mongodb", "mongodb+srv")
CLICKHOUSE_SCHEMES = ("clickhouse", "clickhouses", "clickhouse+http", "clickhouse+https")
MSSQL_SCHEMES = ("mssql", "mssql+pyodbc", "sqlserver")
# ``elasticsearch://`` uses HTTPS (the Elasticsearch 8 default); ``+http`` opts out.
SEARCH_SCHEMES = {
    "elasticsearch": "https",
    "elasticsearch+https": "https",
    "elasticsearch+http": "http",
    "opensearch": "https",
    "opensearch+https": "https",
    "opensearch+http": "http",
}


def search_endpoint(db_uri: str) -> str:
    """Turn an ``elasticsearch://`` / ``opensearch://`` URI into the HTTP(S) endpoint URL.

    Args:
        db_uri: For example ``elasticsearch://user:pass@host:9200`` or
            ``opensearch+http://localhost:9200``.

    Returns:
        The endpoint, e.g. ``https://user:pass@host:9200``.
    """
    parsed = urlparse(db_uri)
    scheme = SEARCH_SCHEMES[parsed.scheme.lower()]
    return urlunparse(parsed._replace(scheme=scheme, path="", params="", query="", fragment=""))


class DatabaseLoader:
    """Simplified interface for loading data to databases."""

    def __init__(self):
        self.ingester = Ingester()

    def load(
        self,
        input_file: str,
        db_uri: str,
        table: str,
        mode: str = "append",
        create_table: bool = False,
        upsert_key: str | None = None,
        source_table: str | None = None,
        start_page: int = 0,
        trust: bool = False,
        **options,
    ):
        """Load data from file to database table.

        Args:
            input_file: Path to input file
            db_uri: Database connection URI
            table: Table name
            mode: Load mode ('append', 'replace', 'upsert')
            create_table: Auto-create table from schema
            upsert_key: Key field(s) for upsert mode (comma-separated)
            source_table: Source table or sheet name for multi-table files
            start_page: 0-based Excel sheet index when ``source_table`` is omitted
            trust: Acknowledge pickle deserialization risk
            **options: Additional options passed to ingester
        """
        scheme = urlparse(db_uri).scheme.lower()
        if scheme in MONGODB_SCHEMES or scheme in SEARCH_SCHEMES:
            self._load_document_store(input_file, db_uri, scheme, table, mode, upsert_key, options)
            return
        if scheme in CLICKHOUSE_SCHEMES or scheme in MSSQL_SCHEMES:
            dbtype = "clickhouse" if scheme in CLICKHOUSE_SCHEMES else "mssql"
            logger.info("Loading %s to %s table %s", input_file, dbtype, table)
            self.ingester.ingest_single(
                input_file,
                db_uri,
                "",
                table,
                {
                    "dbtype": dbtype,
                    "mode": mode,
                    "create_table": create_table,
                    "upsert_key": upsert_key,
                    "table": source_table,
                    "start_page": start_page,
                    "trust": trust,
                    **options,
                },
            )
            return

        # Parse database URI to determine type
        from ..common.db_connection import DatabaseConnectionError, parse_db_uri

        try:
            db_type, params = parse_db_uri(db_uri)
        except DatabaseConnectionError as e:
            raise DatabaseError(f"Invalid database URI: {e}", connection_uri=db_uri) from e
        except Exception as e:
            raise DatabaseError(f"Failed to parse database URI: {e}", connection_uri=db_uri) from e

        # Extract database name from params
        db_name = params.get("database")
        if not db_name and db_type == "sqlite":
            # For SQLite, database name is not needed - use empty string or None
            # The ingester will handle SQLite URIs directly
            db_name = ""
        elif not db_name:
            raise ValidationError(
                f"Database name is required for {db_type}. Provide it in the URI (e.g., postgresql://user:pass@host/dbname)",
                field="db_uri",
            )

        # Prepare options for ingester
        ingest_options = {
            "dbtype": db_type,
            "mode": mode,
            "create_table": create_table,
            "upsert_key": upsert_key,
            "table": source_table,
            "start_page": start_page,
            "trust": trust,
            **options,
        }

        # Call ingester
        logger.info(f"Loading {input_file} to {db_type} database table {table}")
        self.ingester.ingest_single(input_file, db_uri, db_name, table, ingest_options)

    def _load_document_store(
        self,
        input_file: str,
        db_uri: str,
        scheme: str,
        table: str,
        mode: str,
        upsert_key: str | None,
        options: dict,
    ) -> None:
        """Load into MongoDB (database from the URI path) or Elasticsearch/OpenSearch."""
        # MongoDB can drop the collection first; search indexes are only appended to.
        supported = ("append", "replace") if scheme in MONGODB_SCHEMES else ("append",)
        if mode not in supported:
            raise ValidationError(
                f"Mode '{mode}' is not supported for {scheme}:// targets",
                field="mode",
                suggestions=list(supported),
            )
        if upsert_key:
            raise ValidationError(
                f"--upsert-key is not supported for {scheme}:// targets", field="upsert_key"
            )
        ingest_options = {**options, "drop": mode == "replace"}
        if scheme in MONGODB_SCHEMES:
            db_name = unquote(urlparse(db_uri).path.lstrip("/").split("/")[0])
            if not db_name:
                raise ValidationError(
                    "MongoDB URIs need a database name, e.g. mongodb://localhost:27017/mydb",
                    field="db",
                )
            ingest_options["dbtype"] = "mongodb"
            target_uri = db_uri
        else:
            db_name = ""
            ingest_options["dbtype"] = "elasticsearch"
            target_uri = search_endpoint(db_uri)
        logger.info(f"Loading {input_file} to {ingest_options['dbtype']} {table}")
        self.ingester.ingest_single(input_file, target_uri, db_name, table, ingest_options)
