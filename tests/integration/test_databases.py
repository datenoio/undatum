"""Round-trip tests against real database servers.

Each test runs only when its connection variable is set, so the regular suite
skips them; the CI ``db-integration`` job starts service containers and sets:

- ``UNDATUM_TEST_POSTGRES_URI`` (e.g. ``postgresql://postgres:postgres@localhost:5432/undatum``)
- ``UNDATUM_TEST_MYSQL_URI`` (e.g. ``mysql://root:root@127.0.0.1:3306/undatum``)
- ``UNDATUM_TEST_MONGO_URI`` (e.g. ``mongodb://localhost:27017``)
- ``UNDATUM_TEST_ELASTIC_URI`` (e.g. ``http://localhost:9200``)
- ``UNDATUM_TEST_CLICKHOUSE_URI`` (e.g. ``clickhouse://undatum:undatum@localhost:8123/undatum``)
- ``UNDATUM_TEST_MSSQL_URI`` (e.g.
  ``mssql://sa:Undatum_Pass1@localhost:1433/master?TrustServerCertificate=yes``)
"""

import os
import uuid

import pytest
from typer.testing import CliRunner

from undatum.core import app

pytestmark = pytest.mark.integration

runner = CliRunner()

ROWS = [
    {"id": 1, "name": "Alice", "city": "Berlin"},
    {"id": 2, "name": "Bob", "city": "Paris"},
    {"id": 3, "name": "Carol", "city": "Tbilisi"},
]


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is not set")
    return value


@pytest.fixture
def sample_csv(tmp_path):
    path = tmp_path / "people.csv"
    lines = ["id,name,city"] + [f"{r['id']},{r['name']},{r['city']}" for r in ROWS]
    path.write_text("\n".join(lines) + "\n", encoding="utf8")
    return str(path)


def _table_name() -> str:
    return f"people_{uuid.uuid4().hex[:8]}"


def test_postgres_load_round_trip(sample_csv):
    psycopg2 = pytest.importorskip("psycopg2")
    uri = _env("UNDATUM_TEST_POSTGRES_URI")
    table = _table_name()
    result = runner.invoke(
        app, ["db", "load", sample_csv, "--db", uri, "--table", table, "--create-table"]
    )
    assert result.exit_code == 0, result.output
    with psycopg2.connect(uri) as conn, conn.cursor() as cur:
        cur.execute(f'SELECT name FROM "{table}" ORDER BY id')
        assert [row[0] for row in cur.fetchall()] == ["Alice", "Bob", "Carol"]
        cur.execute(f'DROP TABLE "{table}"')


def test_mysql_load_round_trip(sample_csv):
    pymysql = pytest.importorskip("pymysql")
    uri = _env("UNDATUM_TEST_MYSQL_URI")
    table = _table_name()
    result = runner.invoke(
        app, ["db", "load", sample_csv, "--db", uri, "--table", table, "--create-table"]
    )
    assert result.exit_code == 0, result.output

    from undatum.common.db_connection import parse_server_uri

    params = parse_server_uri(uri, ("mysql",), default_port=3306)
    conn = pymysql.connect(**params)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT name FROM `{table}` ORDER BY id")
            assert [row[0] for row in cur.fetchall()] == ["Alice", "Bob", "Carol"]
            cur.execute(f"DROP TABLE `{table}`")
        conn.commit()
    finally:
        conn.close()


def test_clickhouse_load_round_trip(sample_csv):
    pytest.importorskip("clickhouse_connect")
    import clickhouse_connect

    from undatum.cmds.ingester.clickhouse_backend import connection_args

    uri = _env("UNDATUM_TEST_CLICKHOUSE_URI")
    table = _table_name()
    for mode in ("append", "replace"):  # replace leaves the rows of one load
        result = runner.invoke(
            app,
            [
                "db",
                "load",
                sample_csv,
                "--db",
                uri,
                "--table",
                table,
                "--create-table",
                "--mode",
                mode,
            ],
        )
        assert result.exit_code == 0, result.output
    client = clickhouse_connect.get_client(**connection_args(uri))
    try:
        rows = client.query(f"SELECT id, name FROM `{table}` ORDER BY id").result_rows
        assert rows == [(1, "Alice"), (2, "Bob"), (3, "Carol")]
    finally:
        client.command(f"DROP TABLE IF EXISTS `{table}`")
        client.close()


def test_mssql_load_round_trip(sample_csv, tmp_path):
    pyodbc = pytest.importorskip("pyodbc")
    from undatum.cmds.ingester.mssql_backend import connection_string

    uri = _env("UNDATUM_TEST_MSSQL_URI")
    table = _table_name()
    result = runner.invoke(
        app,
        [
            "db",
            "load",
            sample_csv,
            "--db",
            uri,
            "--table",
            table,
            "--create-table",
            "--mode",
            "upsert",
            "--upsert-key",
            "id",
        ],
    )
    assert result.exit_code == 0, result.output
    update = tmp_path / "update.csv"
    update.write_text("id,name,city\n2,Robert,Paris\n4,Dan,Rome\n", encoding="utf8")
    result = runner.invoke(
        app,
        [
            "db",
            "load",
            str(update),
            "--db",
            uri,
            "--table",
            table,
            "--mode",
            "upsert",
            "--upsert-key",
            "id",
        ],
    )
    assert result.exit_code == 0, result.output
    conn = pyodbc.connect(connection_string(uri))
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT id, name FROM [{table}] ORDER BY id")
        assert [tuple(r) for r in cursor.fetchall()] == [
            (1, "Alice"),
            (2, "Robert"),
            (3, "Carol"),
            (4, "Dan"),
        ]
        cursor.execute(f"DROP TABLE [{table}]")
        conn.commit()
    finally:
        conn.close()


def test_mongodb_ingest_round_trip(sample_csv):
    pymongo = pytest.importorskip("pymongo")
    uri = _env("UNDATUM_TEST_MONGO_URI")
    collection = _table_name()
    result = runner.invoke(app, ["ingest", sample_csv, uri, "undatum_test", collection])
    assert result.exit_code == 0, result.output
    client = pymongo.MongoClient(uri)
    try:
        coll = client["undatum_test"][collection]
        assert coll.count_documents({}) == len(ROWS)
        coll.drop()
    finally:
        client.close()


def test_elasticsearch_ingest_round_trip(sample_csv):
    elasticsearch = pytest.importorskip("elasticsearch")
    uri = _env("UNDATUM_TEST_ELASTIC_URI")
    index = _table_name()
    result = runner.invoke(
        app,
        ["ingest", sample_csv, uri, "unused", index, "--dbtype", "elasticsearch", "--doc-id", "id"],
    )
    assert result.exit_code == 0, result.output
    client = elasticsearch.Elasticsearch(uri)
    try:
        client.indices.refresh(index=index)
        assert client.count(index=index)["count"] == len(ROWS)
        client.indices.delete(index=index)
    finally:
        client.close()
