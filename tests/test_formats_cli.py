"""Tests for the `undatum formats` catalog command."""

import json

import pytest
from typer.testing import CliRunner

from undatum.core import app

runner = CliRunner()


class TestFormatsCommand:
    def test_list_default(self):
        result = runner.invoke(app, ["formats", "list"])
        assert result.exit_code == 0
        assert "csv" in result.stdout
        assert "parquet" in result.stdout
        assert "Maturity" in result.stdout

    def test_list_json(self):
        result = runner.invoke(app, ["formats", "list", "--json"])
        assert result.exit_code == 0
        document = json.loads(result.stdout)
        assert document["schema"] == "undatum.formats/1"
        data = document["formats"]
        ids = {row["id"] for row in data}
        assert "csv" in ids
        assert len(data) > 50

    def test_list_writable_filter(self):
        result = runner.invoke(app, ["formats", "list", "--writable", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)["formats"]
        assert all(row["writable"] for row in data)

    def test_list_json_includes_capabilities(self):
        result = runner.invoke(app, ["formats", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)["formats"]
        assert "capabilities" in data[0]
        csv_row = next(row for row in data if row["id"] == "csv")
        assert csv_row["capabilities"].get("readable") is True

    def test_list_capabilities_columns(self):
        result = runner.invoke(app, ["formats", "list", "--capabilities"])
        assert result.exit_code == 0
        # Capability table still lists formats (headers may clip in narrow terminals)
        assert "csv" in result.stdout

    def test_list_json_includes_maturity(self):
        result = runner.invoke(app, ["formats", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)["formats"]
        parquet = next(row for row in data if row["id"] == "parquet")
        assert parquet.get("maturity") in {"stable", "experimental", "partial"}
        assert "native_bulk_read" in parquet["capabilities"]
        assert "native_bulk_write" in parquet["capabilities"]

    def test_describe(self):
        result = runner.invoke(app, ["formats", "describe", "parquet"])
        assert result.exit_code == 0
        assert "parquet" in result.stdout.lower()
        assert "Read memory" in result.stdout
        assert "Selection" in result.stdout
        assert "Codecs" in result.stdout
        assert "Flat/tabular" in result.stdout
        assert "Native bulk read" in result.stdout
        assert "Native bulk write" in result.stdout

    def test_describe_example_args(self):
        result = runner.invoke(app, ["formats", "describe", "xml"])
        assert result.exit_code == 0
        assert "Example args" in result.stdout
        assert "tagname=" in result.stdout

    def test_describe_json(self):
        result = runner.invoke(app, ["formats", "describe", "csv", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert data["id"] == "csv"
        assert "capabilities" in data

    def test_describe_unknown(self):
        result = runner.invoke(app, ["formats", "describe", "totallynotaformat"])
        assert result.exit_code == 1

    def test_export(self):
        result = runner.invoke(app, ["formats", "export", "--no-capabilities"])
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        assert "csv" in data
        assert len(data) > 50

    def test_export_to_file(self, tmp_path):
        out = tmp_path / "catalog.json"
        result = runner.invoke(app, ["formats", "export", "--output", str(out)])
        assert result.exit_code == 0
        assert out.exists()
        data = json.loads(out.read_text())
        assert "csv" in data


class TestFormatsTables:
    def test_xlsx_sheets(self, tmp_path):
        pytest.importorskip("openpyxl")
        from openpyxl import Workbook

        path = tmp_path / "wb.xlsx"
        wb = Workbook()
        wb.active.title = "Sheet1"
        wb.create_sheet("Cities")
        wb.save(path)

        result = runner.invoke(app, ["formats", "tables", str(path), "--json"])
        assert result.exit_code == 0, result.stdout
        data = json.loads(result.stdout)
        assert "Sheet1" in data["tables"]
        assert "Cities" in data["tables"]

    def test_sqlite_tables(self, tmp_path):
        import sqlite3

        path = tmp_path / "data.sqlite"
        conn = sqlite3.connect(path)
        conn.execute("CREATE TABLE people (id INTEGER)")
        conn.execute("CREATE TABLE cities (name TEXT)")
        conn.commit()
        conn.close()

        result = runner.invoke(app, ["formats", "tables", str(path), "--json"])
        assert result.exit_code == 0, result.stdout
        data = json.loads(result.stdout)
        assert set(data["tables"]) >= {"people", "cities"}

    def test_missing_file(self):
        result = runner.invoke(app, ["formats", "tables", "no-such-file.xlsx"])
        assert result.exit_code == 1

    def test_help(self):
        result = runner.invoke(app, ["formats", "tables", "--help"])
        assert result.exit_code == 0
        assert "tables" in result.stdout.lower()
