"""Microsoft SQL Server ingester backend (``pyodbc``, extra ``undatum[mssql]``)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from ...common.errors import DependencyError, ValidationError
from .base import BasicIngester
from .types import MSSQL_TYPES, convert, infer_kinds

logger = logging.getLogger(__name__)

DEFAULT_DRIVER = "ODBC Driver 18 for SQL Server"


def _quote(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def _table(name: str) -> str:
    """``schema.table`` or ``table``, each part bracket-quoted."""
    return ".".join(_quote(part) for part in name.split(".", 1))


def connection_string(uri: str) -> str:
    """An ODBC connection string from ``mssql://user:pass@host:1433/db?driver=...``.

    Query parameters become ODBC keywords (``TrustServerCertificate=yes``, ``Encrypt=no``,
    ...); ``driver`` defaults to ``ODBC Driver 18 for SQL Server``.
    """
    parsed = urlparse(uri)
    query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
    driver = query.pop("driver", DEFAULT_DRIVER)
    host = parsed.hostname or "localhost"
    server = f"{host},{parsed.port}" if parsed.port else host
    parts = [f"DRIVER={{{driver}}}", f"SERVER={server}"]
    database = parsed.path.lstrip("/")
    if database:
        parts.append(f"DATABASE={unquote(database)}")
    if parsed.username:
        parts.append(f"UID={unquote(parsed.username)}")
        parts.append("PWD={" + unquote(parsed.password or "").replace("}", "}}") + "}")
    else:
        parts.append("Trusted_Connection=yes")
    parts += [f"{key}={value}" for key, value in query.items()]
    return ";".join(parts)


class MSSQLIngester(BasicIngester):
    """Batched inserts into SQL Server with ``fast_executemany``.

    Args:
        uri: ``mssql://user:password@host:1433/database``.
        table: Table name (``schema.table`` allowed).
        mode: ``append``, ``replace`` (delete rows before the first batch) or ``upsert``
            (``MERGE`` on ``upsert_key``).
        create_table: Create the table from the first batch when it does not exist.
        upsert_key: Key column(s) for ``upsert`` (comma-separated or a list).
        connection: A DB-API connection to use instead of connecting (tests).
    """

    def __init__(
        self,
        uri: str,
        table: str,
        mode: str = "append",
        create_table: bool = False,
        upsert_key: str | list[str] | None = None,
        connection: Any = None,
    ) -> None:
        if mode not in ("append", "replace", "upsert"):
            raise ValidationError(
                f"Unknown --mode '{mode}'",
                field="mode",
                suggestions=["append", "replace", "upsert"],
            )
        keys = (
            [k.strip() for k in upsert_key.split(",")]
            if isinstance(upsert_key, str)
            else list(upsert_key or [])
        )
        if mode == "upsert" and not keys:
            raise ValidationError("--mode upsert needs --upsert-key", field="upsert_key")
        self.table = table
        self.mode = mode
        self.create_table = create_table
        self.keys = keys
        self._columns: list[tuple[str, str, bool]] | None = None
        self._first_batch = True
        if connection is None:
            try:
                import pyodbc
            except ImportError as exc:
                raise DependencyError(
                    "pyodbc",
                    feature="loading into SQL Server",
                    install_command='pip install "undatum[mssql]"',
                ) from exc
            connection = pyodbc.connect(connection_string(uri), autocommit=False)
        self.conn = connection

    def check_connection(self) -> None:
        """Run ``SELECT 1``."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()

    def create_table_sql(self, columns: list[tuple[str, str, bool]]) -> str:
        """``CREATE TABLE`` guarded by ``IF OBJECT_ID(...) IS NULL``."""
        definitions = []
        for name, kind, nullable in columns:
            sql_type = MSSQL_TYPES[kind]
            if name in self.keys and kind == "string":
                sql_type = "NVARCHAR(450)"  # index key size limit
            null = "NULL" if nullable and name not in self.keys else "NOT NULL"
            definitions.append(f"{_quote(name)} {sql_type} {null}")
        if self.keys:
            definitions.append(f"PRIMARY KEY ({', '.join(_quote(k) for k in self.keys)})")
        literal = self.table.replace("'", "''")
        return (
            f"IF OBJECT_ID(N'{literal}', N'U') IS NULL "
            f"CREATE TABLE {_table(self.table)} ({', '.join(definitions)})"
        )

    def merge_sql(self, names: list[str], staging: str) -> str:
        """``MERGE`` from ``staging`` into the table on the upsert keys."""
        on = " AND ".join(f"t.{_quote(k)} = s.{_quote(k)}" for k in self.keys)
        updates = [n for n in names if n not in self.keys]
        columns = ", ".join(_quote(n) for n in names)
        values = ", ".join(f"s.{_quote(n)}" for n in names)
        sql = f"MERGE {_table(self.table)} WITH (HOLDLOCK) AS t USING {staging} AS s ON {on} "
        if updates:
            assignments = ", ".join(f"t.{_quote(n)} = s.{_quote(n)}" for n in updates)
            sql += f"WHEN MATCHED THEN UPDATE SET {assignments} "
        return sql + f"WHEN NOT MATCHED THEN INSERT ({columns}) VALUES ({values});"

    def _prepare(self, batch: list[dict[str, Any]]) -> None:
        cursor = self.conn.cursor()
        inferred = infer_kinds(batch)
        if self.create_table:
            cursor.execute(self.create_table_sql(inferred))
        if self.mode == "replace":
            cursor.execute(f"DELETE FROM {_table(self.table)}")
        self.conn.commit()
        self._columns = inferred

    def ingest(self, batch: list[dict[str, Any]]) -> None:
        """Insert (or merge) one batch in one transaction."""
        if not batch:
            return
        if self._first_batch:
            self._prepare(batch)
            self._first_batch = False
        assert self._columns is not None
        names = [name for name, _, _ in self._columns]
        rows = [tuple(convert(r.get(name), kind) for name, kind, _ in self._columns) for r in batch]
        placeholders = ", ".join("?" for _ in names)
        columns = ", ".join(_quote(n) for n in names)
        cursor = self.conn.cursor()
        cursor.fast_executemany = True
        try:
            if self.mode == "upsert":
                staging = "#undatum_staging"
                cursor.execute(f"SELECT TOP 0 {columns} INTO {staging} FROM {_table(self.table)}")
                cursor.executemany(
                    f"INSERT INTO {staging} ({columns}) VALUES ({placeholders})", rows
                )
                cursor.execute(self.merge_sql(names, staging))
                cursor.execute(f"DROP TABLE {staging}")
            else:
                cursor.executemany(
                    f"INSERT INTO {_table(self.table)} ({columns}) VALUES ({placeholders})", rows
                )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def close(self) -> None:
        """Close the connection."""
        self.conn.close()
