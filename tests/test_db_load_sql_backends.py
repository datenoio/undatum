"""ClickHouse and SQL Server loaders (fake clients; live servers in tests/integration)."""

from __future__ import annotations

import sys
import types

import pytest
from typer.testing import CliRunner

from undatum.cmds.ingester.clickhouse_backend import ClickHouseIngester, connection_args
from undatum.cmds.ingester.mssql_backend import MSSQLIngester, connection_string
from undatum.cmds.ingester.types import convert, infer_kinds
from undatum.common.errors import DatabaseError, ValidationError
from undatum.core import app

ROWS = [
    {"id": "1", "name": "Alice", "score": "1.5", "ok": "true", "code": "007", "note": ""},
    {"id": "2", "name": "Bob", "score": "2", "ok": "false", "code": "010", "note": "x"},
]


def test_infer_kinds():
    assert infer_kinds(ROWS) == [
        ("id", "integer", False),
        ("name", "string", False),
        ("score", "number", False),
        ("ok", "boolean", False),
        ("code", "string", False),  # leading zeros stay text
        ("note", "string", True),
    ]
    assert infer_kinds([{"a": 1}, {"a": 2.5}, {"b": None}]) == [
        ("a", "number", True),
        ("b", "string", True),
    ]
    assert convert("1.5", "number") == 1.5 and convert("", "integer") is None
    assert convert({"x": 1}, "string") == '{"x": 1}'


def test_clickhouse_uri():
    assert connection_args("clickhouse://u:p%40ss@db:9000/sales") == {
        "host": "db",
        "port": 9000,
        "username": "u",
        "password": "p@ss",
        "secure": False,
        "database": "sales",
    }
    secure = connection_args("clickhouses://h/")
    assert secure["secure"] is True and secure["port"] == 8443 and "database" not in secure


def test_mssql_connection_string():
    text = connection_string("mssql://sa:pa%3Bss@db:1433/sales?TrustServerCertificate=yes")
    assert text == (
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=db,1433;DATABASE=sales;UID=sa;"
        "PWD={pa;ss};TrustServerCertificate=yes"
    )
    assert "Trusted_Connection=yes" in connection_string("mssql://host/db?driver=FreeTDS")
    assert "DRIVER={FreeTDS}" in connection_string("mssql://host/db?driver=FreeTDS")


class FakeClickHouse:
    def __init__(self, exists=False):
        self.commands: list[str] = []
        self.inserts: list[tuple[str, list, list]] = []
        self.exists = exists

    def command(self, sql):
        self.commands.append(sql)
        if sql.startswith("EXISTS TABLE"):
            return 1 if self.exists else 0
        return None

    def insert(self, table, rows, column_names):
        self.inserts.append((table, rows, column_names))

    def close(self):
        self.commands.append("<closed>")


def test_clickhouse_create_and_insert():
    client = FakeClickHouse()
    loader = ClickHouseIngester("clickhouse://h", "people", create_table=True, client=client)
    loader.ingest(ROWS)
    loader.ingest([{"id": "3", "name": "Carol", "extra": "new"}])
    create = next(c for c in client.commands if c.startswith("CREATE TABLE"))
    assert "`id` Int64" in create and "`score` Float64" in create and "`ok` Bool" in create
    assert "`note` Nullable(String)" in create
    assert create.endswith("ENGINE = MergeTree ORDER BY tuple()")
    table, rows, names = client.inserts[0]
    assert names == ["id", "name", "score", "ok", "code", "note"]
    assert rows[0] == [1, "Alice", 1.5, True, "007", None]
    assert client.inserts[1][2][-1] == "extra"  # new column appended


def test_clickhouse_modes():
    client = FakeClickHouse(exists=True)
    ClickHouseIngester("clickhouse://h", "t", mode="replace", client=client).ingest(ROWS)
    assert client.commands[0] == "TRUNCATE TABLE IF EXISTS `t`"
    client = FakeClickHouse()
    loader = ClickHouseIngester(
        "clickhouse://h",
        "t",
        mode="replace",
        create_table=True,
        table_engine="ReplacingMergeTree ORDER BY id",
        client=client,
    )
    loader.ingest(ROWS)
    assert client.commands[0] == "DROP TABLE IF EXISTS `t`"
    assert client.commands[-1].endswith("ENGINE = ReplacingMergeTree ORDER BY id")
    with pytest.raises(ValidationError):
        ClickHouseIngester("clickhouse://h", "t", mode="upsert", client=FakeClickHouse())


class FakeCursor:
    def __init__(self, log, fail_on=None):
        self.log = log
        self.fail_on = fail_on
        self.fast_executemany = False

    def execute(self, sql, *params):
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("boom")
        self.log.append(("execute", sql))

    def executemany(self, sql, rows):
        self.log.append(("executemany", sql, list(rows), self.fast_executemany))

    def fetchone(self):
        return (1,)


class FakeConnection:
    def __init__(self, fail_on=None):
        self.log: list = []
        self.fail_on = fail_on

    def cursor(self):
        return FakeCursor(self.log, self.fail_on)

    def commit(self):
        self.log.append(("commit",))

    def rollback(self):
        self.log.append(("rollback",))

    def close(self):
        self.log.append(("close",))


def test_mssql_create_insert_and_replace():
    conn = FakeConnection()
    loader = MSSQLIngester(
        "mssql://h/db", "dbo.people", mode="replace", create_table=True, connection=conn
    )
    loader.ingest(ROWS)
    sql = [entry[1] for entry in conn.log if entry[0] == "execute"]
    assert sql[0].startswith(
        "IF OBJECT_ID(N'dbo.people', N'U') IS NULL CREATE TABLE [dbo].[people]"
    )
    assert "[id] BIGINT NOT NULL" in sql[0] and "[note] NVARCHAR(MAX) NULL" in sql[0]
    assert sql[1] == "DELETE FROM [dbo].[people]"
    inserted = next(entry for entry in conn.log if entry[0] == "executemany")
    assert inserted[1].startswith("INSERT INTO [dbo].[people] ([id], [name]")
    assert inserted[2][0] == (1, "Alice", 1.5, True, "007", None)
    assert inserted[3] is True  # fast_executemany


def test_mssql_upsert_merge():
    conn = FakeConnection()
    loader = MSSQLIngester(
        "mssql://h/db", "t", mode="upsert", upsert_key="id", create_table=True, connection=conn
    )
    loader.ingest(ROWS)
    sql = [entry[1] for entry in conn.log if entry[0] == "execute"]
    assert "PRIMARY KEY ([id])" in sql[0]
    merge = next(s for s in sql if s.startswith("MERGE"))
    assert "ON t.[id] = s.[id]" in merge
    assert "WHEN MATCHED THEN UPDATE SET t.[name] = s.[name]" in merge
    assert "WHEN NOT MATCHED THEN INSERT" in merge
    with pytest.raises(ValidationError):
        MSSQLIngester("mssql://h/db", "t", mode="upsert", connection=FakeConnection())


def test_mssql_rolls_back_a_failed_batch():
    conn = FakeConnection(fail_on="MERGE")
    loader = MSSQLIngester("mssql://h/db", "t", mode="upsert", upsert_key="id", connection=conn)
    with pytest.raises(RuntimeError):
        loader.ingest(ROWS)
    assert conn.log[-1] == ("rollback",)


def test_db_load_routes_clickhouse(tmp_path, monkeypatch):
    client = FakeClickHouse()
    module = types.ModuleType("clickhouse_connect")
    module.get_client = lambda **kwargs: client
    monkeypatch.setitem(sys.modules, "clickhouse_connect", module)
    path = tmp_path / "people.csv"
    path.write_text("id,name\n1,Alice\n2,Bob\n")
    result = CliRunner().invoke(
        app,
        [
            "db",
            "load",
            str(path),
            "--db",
            "clickhouse://localhost/sales",
            "--table",
            "people",
            "--create-table",
        ],
    )
    assert result.exit_code == 0, result.output
    assert client.inserts[0][1] == [[1, "Alice"], [2, "Bob"]]


def test_failed_rows_are_an_error(tmp_path):
    path = tmp_path / "people.csv"
    path.write_text("id,name\n1,Alice\n")
    result = CliRunner().invoke(
        app,
        ["db", "load", str(path), "--db", f"sqlite:///{tmp_path / 'x.db'}", "--table", "missing"],
    )
    assert isinstance(result.exception, DatabaseError)
    assert "1 of 1 rows were not loaded" in str(result.exception)
