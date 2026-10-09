"""Tests for analyze command with semicolon-delimited CSV."""

from undatum.cmds.analyzer import Analyzer, analyze


class TestAnalyzeSemicolonCsv:
    """Integration tests for analyze with semicolon CSV."""

    def test_analyze_auto_detect_delimiter(self, semicolon_csv):
        report = analyze(semicolon_csv, engine="auto")
        assert report.tables
        field_names = {f.name for f in report.tables[0].fields}
        assert field_names == {"id", "name", "city"}
        assert report.total_records == 2

    def test_analyze_explicit_delimiter(self, semicolon_csv):
        report = analyze(semicolon_csv, delimiter=";", engine="duckdb")
        field_names = {f.name for f in report.tables[0].fields}
        assert field_names == {"id", "name", "city"}

    def test_analyzer_cli_wrapper(self, semicolon_csv, capsys):
        Analyzer().analyze(
            semicolon_csv,
            {
                "engine": "auto",
                "use_pandas": False,
                "outtype": "json",
                "output": None,
                "autodoc": False,
                "lang": "English",
                "delimiter": ";",
                "encoding": None,
            },
        )
        import json

        captured = capsys.readouterr()
        report = json.loads(captured.out)
        field_names = {f["name"] for f in report["tables"][0]["fields"]}
        assert field_names == {"id", "name", "city"}
