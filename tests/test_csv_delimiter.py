"""Tests for CSV delimiter handling in iterable and DuckDB paths."""

from undatum.cmds.statistics import StatProcessor
from undatum.common.command_utils import (
    apply_iterable_csv_delimiter,
    duckdb_read_csv_expr,
    resolve_csv_delimiter,
)
from undatum.common.s3_iterable import open_iterable_with_s3


class TestResolveCsvDelimiter:
    """Test delimiter resolution helpers."""

    def test_explicit_delimiter(self, semicolon_csv):
        result = resolve_csv_delimiter(
            {"delimiter": ";"},
            filename=semicolon_csv,
            filetype="csv",
        )
        assert result == ";"

    def test_auto_detect_semicolon(self, semicolon_csv):
        result = resolve_csv_delimiter({}, filename=semicolon_csv, filetype="csv")
        assert result == ";"

    def test_sniffer_prefers_semicolon_with_commas_in_quotes(self, semicolon_csv):
        from undatum.utils import detect_delimiter

        assert detect_delimiter(semicolon_csv) == ";"


class TestIterableCsvDelimiter:
    """Test iterable reader delimiter application."""

    def test_open_iterable_with_explicit_delimiter(self, semicolon_csv):
        with open_iterable_with_s3(
            semicolon_csv, mode="r", iterableargs={"delimiter": ";"}
        ) as iterable:
            row = next(iter(iterable))
        assert set(row.keys()) == {"id", "name", "city"}
        assert row["name"] == "Acme, Inc"

    def test_open_iterable_auto_detect_delimiter(self, semicolon_csv):
        with open_iterable_with_s3(semicolon_csv, mode="r", iterableargs={}) as iterable:
            row = next(iter(iterable))
        assert set(row.keys()) == {"id", "name", "city"}

    def test_apply_iterable_csv_delimiter_on_open_iterable(self, semicolon_csv):
        from iterable.helpers.detect import open_iterable

        with open_iterable(semicolon_csv, mode="r", iterableargs={}) as iterable:
            apply_iterable_csv_delimiter(iterable, semicolon_csv, {"delimiter": ";"})
            row = next(iter(iterable))
        assert set(row.keys()) == {"id", "name", "city"}


class TestDuckdbReadCsvExpr:
    """Test DuckDB read_csv expression builder."""

    def test_includes_delimiter_and_strict_mode(self):
        expr = duckdb_read_csv_expr("/tmp/data.csv", ";")
        assert "delim=';'" in expr
        assert "strict_mode=false" in expr
        assert "quote=" in expr


class TestStatsSemicolonCsv:
    """Integration tests for stats command with semicolon CSV."""

    def test_stats_iterable_engine_semicolon(self, semicolon_csv, capsys):
        processor = StatProcessor()
        processor.stats(
            semicolon_csv,
            {"delimiter": ";", "engine": "iterable", "no_progress": True},
        )
        captured = capsys.readouterr()
        assert "Dataset Profile" in captured.out
        # Rich table truncates field names; verify three distinct columns were profiled
        assert captured.out.count("100.0%") >= 3

    def test_stats_duckdb_engine_semicolon(self, semicolon_csv, capsys):
        processor = StatProcessor()
        processor.stats(
            semicolon_csv,
            {"delimiter": ";", "engine": "duckdb", "no_progress": True},
        )
        captured = capsys.readouterr()
        assert "Dataset Profile" in captured.out
        assert captured.out.count("100.0%") >= 3
