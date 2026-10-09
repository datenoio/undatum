"""ClickHouse ingester backend (``clickhouse-connect``, extra ``undatum[clickhouse]``)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from ...common.errors import DependencyError, ValidationError
from .base import BasicIngester
from .types import CLICKHOUSE_TYPES, convert, infer_kinds

logger = logging.getLogger(__name__)

DEFAULT_TABLE_ENGINE = "MergeTree ORDER BY tuple()"


def _quote(name: str) -> str:
    return "`" + name.replace("\\", "\\\\").replace("`", "\\`") + "`"


def connection_args(uri: str) -> dict[str, Any]:
    """``clickhouse_connect.get_client`` arguments from a ``clickhouse://`` URI.

    ``clickhouse://user:pass@host:8123/db`` (HTTP); ``clickhouses://`` or ``?secure=true``
    for HTTPS (port 8443 by default).
    """
    parsed = urlparse(uri)
    query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
    secure = parsed.scheme.lower() in ("clickhouses", "clickhouse+https") or query.get(
        "secure", ""
    ).lower() in ("1", "true", "yes")
    args: dict[str, Any] = {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or (8443 if secure else 8123),
        "username": unquote(parsed.username) if parsed.username else "default",
        "password": unquote(parsed.password) if parsed.password else "",
        "secure": secure,
    }
    database = parsed.path.lstrip("/")
    if database:
        args["database"] = database
    return args


class ClickHouseIngester(BasicIngester):
    """Batched inserts into a ClickHouse table.

    Args:
        uri: ``clickhouse://user:password@host:8123/database``.
        table: Table name.
        mode: ``append`` or ``replace`` (truncates the table before the first batch).
        create_table: Create the table from the first batch when it does not exist (with
            ``replace``: drop and create it).
        table_engine: ``ENGINE`` clause for created tables.
        client: A client to use instead of connecting (tests).
    """

    def __init__(
        self,
        uri: str,
        table: str,
        mode: str = "append",
        create_table: bool = False,
        table_engine: str | None = None,
        client: Any = None,
    ) -> None:
        if mode not in ("append", "replace"):
            raise ValidationError(
                f"ClickHouse supports --mode append or replace, not '{mode}'",
                field="mode",
                suggestions=["append", "replace"],
            )
        self.table = table
        self.mode = mode
        self.create_table = create_table
        self.table_engine = table_engine or DEFAULT_TABLE_ENGINE
        self._columns: list[tuple[str, str, bool]] | None = None
        self._first_batch = True
        if client is None:
            try:
                import clickhouse_connect
            except ImportError as exc:
                raise DependencyError(
                    "clickhouse-connect",
                    feature="loading into ClickHouse",
                    install_command='pip install "undatum[clickhouse]"',
                ) from exc
            client = clickhouse_connect.get_client(**connection_args(uri))
        self.client = client

    def check_connection(self) -> None:
        """Run ``SELECT 1``."""
        self.client.command("SELECT 1")

    def _table_exists(self) -> bool:
        return bool(self.client.command(f"EXISTS TABLE {_quote(self.table)}"))

    def create_table_sql(self, columns: list[tuple[str, str, bool]]) -> str:
        """``CREATE TABLE`` for inferred columns (nullable columns are ``Nullable(T)``)."""
        definitions = []
        for name, kind, nullable in columns:
            sql_type = CLICKHOUSE_TYPES[kind]
            definitions.append(
                f"{_quote(name)} {'Nullable(' + sql_type + ')' if nullable else sql_type}"
            )
        return (
            f"CREATE TABLE IF NOT EXISTS {_quote(self.table)} ({', '.join(definitions)}) "
            f"ENGINE = {self.table_engine}"
        )

    def _prepare(self, batch: list[dict[str, Any]]) -> None:
        inferred = infer_kinds(batch)
        if self.create_table:
            if self.mode == "replace":
                self.client.command(f"DROP TABLE IF EXISTS {_quote(self.table)}")
            if not self._table_exists():
                self.client.command(self.create_table_sql(inferred))
                logger.info("Created ClickHouse table %s", self.table)
        elif self.mode == "replace":
            self.client.command(f"TRUNCATE TABLE IF EXISTS {_quote(self.table)}")
        self._columns = inferred

    def ingest(self, batch: list[dict[str, Any]]) -> None:
        """Insert one batch."""
        if not batch:
            return
        if self._first_batch:
            self._prepare(batch)
            self._first_batch = False
        assert self._columns is not None
        known = {name for name, _, _ in self._columns}
        for record in batch:
            for key in record:
                if key not in known:
                    self._columns.append((key, "string", True))
                    known.add(key)
        names = [name for name, _, _ in self._columns]
        rows = [
            [convert(record.get(name), kind) for name, kind, _ in self._columns] for record in batch
        ]
        self.client.insert(self.table, rows, column_names=names)

    def close(self) -> None:
        """Close the client."""
        close = getattr(self.client, "close", None)
        if close is not None:
            close()
