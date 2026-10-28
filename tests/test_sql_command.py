"""Tests for the ad-hoc SQL command."""

import json
import os
import tempfile

import pytest

from undatum.cmds.sql import SqlExecutor, view_name_for_file
from undatum.common.errors import FileNotFoundError as UndatumFileNotFoundError
from undatum.common.errors import UndatumError, ValidationError


@pytest.fixture
def csv_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write("city,amount\nNYC,100\nNYC,50\nLA,70\n")
        path = f.name
    yield path
    os.unlink(path)


@pytest.fixture
def jsonl_file():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write('{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}\n')
        path = f.name
    yield path
    os.unlink(path)


class TestViewNameForFile:
    def test_simple_stem(self):
        assert view_name_for_file("/tmp/sales.csv") == "sales"

    def test_multiple_extensions(self):
        assert view_name_for_file("data.csv.gz") == "data"

    def test_special_characters(self):
        assert view_name_for_file("/tmp/my-data file.csv") == "my_data_file"

    def test_leading_digit(self):
        assert view_name_for_file("2024-sales.csv") == "t_2024_sales"


class TestSqlExecutor:
    def test_query_single_csv_jsonl_output(self, csv_file, capsys):
        SqlExecutor().query(
            "SELECT city, SUM(amount) AS total FROM data GROUP BY city ORDER BY city",
            [csv_file],
        )
        out = capsys.readouterr().out
        rows = [json.loads(line) for line in out.strip().splitlines()]
        assert rows == [{"city": "LA", "total": 70}, {"city": "NYC", "total": 150}]

    def test_query_via_stem_view(self, csv_file, capsys):
        view = view_name_for_file(csv_file)
        SqlExecutor().query(f'SELECT COUNT(*) AS n FROM "{view}"', [csv_file])
        out = capsys.readouterr().out
        assert json.loads(out.strip()) == {"n": 3}

    def test_query_jsonl_input(self, jsonl_file, capsys):
        SqlExecutor().query("SELECT name FROM data WHERE id = 2", [jsonl_file])
        out = capsys.readouterr().out
        assert json.loads(out.strip()) == {"name": "Bob"}

    def test_query_multiple_files(self, csv_file, jsonl_file, capsys):
        v1 = view_name_for_file(csv_file)
        v2 = view_name_for_file(jsonl_file)
        SqlExecutor().query(
            f'SELECT (SELECT COUNT(*) FROM "{v1}") AS a, (SELECT COUNT(*) FROM "{v2}") AS b',
            [csv_file, jsonl_file],
        )
        out = capsys.readouterr().out
        assert json.loads(out.strip()) == {"a": 3, "b": 2}

    def test_csv_output_to_file(self, csv_file):
        with tempfile.NamedTemporaryFile(mode="r", suffix=".csv", delete=False) as f:
            out_path = f.name
        try:
            SqlExecutor().query(
                "SELECT * FROM data WHERE amount > 60 ORDER BY amount",
                [csv_file],
                {"output": out_path, "format": "csv"},
            )
            with open(out_path) as f:
                content = f.read().strip().splitlines()
            assert content[0] == "city,amount"
            assert content[1] == "LA,70"
            assert content[2] == "NYC,100"
        finally:
            os.unlink(out_path)

    def test_parquet_output(self, csv_file):
        pytest.importorskip("duckdb")
        out_path = tempfile.mktemp(suffix=".parquet")
        try:
            SqlExecutor().query(
                "SELECT * FROM data",
                [csv_file],
                {"output": out_path, "format": "parquet"},
            )
            import duckdb

            count = duckdb.sql(f"SELECT COUNT(*) FROM '{out_path}'").fetchall()[0][0]
            assert count == 3
        finally:
            if os.path.exists(out_path):
                os.unlink(out_path)

    def test_empty_query_raises(self, csv_file):
        with pytest.raises(ValidationError):
            SqlExecutor().query("  ", [csv_file])

    def test_no_files_raises(self):
        with pytest.raises(ValidationError):
            SqlExecutor().query("SELECT 1", [])

    def test_invalid_format_raises(self, csv_file):
        with pytest.raises(ValidationError):
            SqlExecutor().query("SELECT 1", [csv_file], {"format": "xml"})

    def test_parquet_to_stdout_raises(self, csv_file):
        with pytest.raises(ValidationError):
            SqlExecutor().query("SELECT 1", [csv_file], {"format": "parquet"})

    def test_missing_file_raises(self):
        with pytest.raises(UndatumFileNotFoundError):
            SqlExecutor().query("SELECT 1", ["/nonexistent/file.csv"])

    def test_invalid_sql_raises(self, csv_file):
        with pytest.raises(UndatumError):
            SqlExecutor().query("SELECT bad syntax FROM", [csv_file])

    def test_fetch_returns_bounded_rows(self, csv_file):
        columns, records, truncated = SqlExecutor().fetch(
            "SELECT city FROM data ORDER BY city", [csv_file], max_rows=2
        )
        assert "city" in columns
        assert len(records) == 2
        assert truncated is True
        columns, records, truncated = SqlExecutor().fetch(
            "SELECT COUNT(*) AS n FROM data", [csv_file], max_rows=10
        )
        assert records[0]["n"] == 3
        assert truncated is False
