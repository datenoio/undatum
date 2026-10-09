"""Regression tests for runtime defects fixed in 1.7.1."""

import pytest
from typer.testing import CliRunner

from undatum.common.db_connection import parse_server_uri
from undatum.common.errors import ValidationError
from undatum.core import app

runner = CliRunner()


def test_server_uri_without_credentials():
    params = parse_server_uri("postgresql://localhost/db", ("postgresql",), default_port=5432)
    assert params == {"host": "localhost", "port": 5432, "database": "db"}


def test_server_uri_decodes_password():
    params = parse_server_uri(
        "mysql://user:p%40ss%3Aword@db.example.com:3307/sales", ("mysql",), default_port=3306
    )
    assert params["password"] == "p@ss:word"
    assert params["port"] == 3307
    assert params["database"] == "sales"


def test_server_uri_rejects_other_scheme():
    with pytest.raises(ValidationError):
        parse_server_uri("mongodb://localhost/db", ("postgresql",), default_port=5432)


def test_slice_without_range_exits_1(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("a\n1\n2\n", encoding="utf8")
    result = runner.invoke(app, ["slice", str(source)])
    assert result.exit_code == 1
    assert isinstance(result.exception, ValidationError), result.exception


def test_sample_without_size_exits_1(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("a\n1\n2\n", encoding="utf8")
    result = runner.invoke(app, ["sample", str(source)])
    assert result.exit_code == 1
    assert isinstance(result.exception, ValidationError), result.exception


@pytest.mark.parametrize("engine", ["duckbd", "pandas"])
def test_unknown_engine_is_a_usage_error(tmp_path, engine):
    source = tmp_path / "data.csv"
    source.write_text("a\n2\n1\n", encoding="utf8")
    result = runner.invoke(app, ["sort", str(source), "--by", "a", "--engine", engine])
    assert result.exit_code == 2
    assert engine in result.output


def test_iterable_engine_alias_still_works(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("a\n2\n1\n", encoding="utf8")
    result = runner.invoke(app, ["sort", str(source), "--by", "a", "--engine", "iterable"])
    assert result.exit_code == 0, result.output


def test_cat_invalid_mode_exits_1(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("a\n1\n", encoding="utf8")
    result = runner.invoke(app, ["cat", str(source), str(source), "--mode", "diagonal"])
    assert result.exit_code == 1
    assert isinstance(result.exception, ValidationError), result.exception


def test_validate_unknown_rule_exits_1(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("email\na@b.com\n", encoding="utf8")
    result = runner.invoke(app, ["validate", str(source), "--fields", "email", "--rule", "emial"])
    assert result.exit_code == 1
    assert isinstance(result.exception, ValidationError), result.exception


def test_validate_stats_is_json(tmp_path):
    import json

    source = tmp_path / "data.csv"
    source.write_text("email\na@b.com\nbad\n", encoding="utf8")
    result = runner.invoke(
        app,
        ["validate", str(source), "--fields", "email", "--rule", "common.email", "--mode", "stats"],
    )
    assert result.exit_code == 0, result.output
    stats = json.loads(result.stdout)
    assert stats["invalid"] == 1


def test_pipeline_template_init_without_terminal(tmp_path):
    """Without a terminal the template is written with its defaults instead of prompting."""
    import subprocess
    import sys

    out = tmp_path / "pipeline.yml"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "undatum",
            "pipeline",
            "templates",
            "init",
            "basic-cleaning",
            "--output",
            str(out),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists()


def test_schema_bulk_creates_output_directory(tmp_path):
    from undatum.cmds.schemer import Schemer

    source = tmp_path / "in"
    source.mkdir()
    (source / "a.jsonl").write_text('{"x": 1}\n', encoding="utf8")
    target = tmp_path / "schemas" / "nested"
    Schemer().extract_schema_bulk(
        str(source), {"mode": "perfile", "output": str(target), "format": "jsonschema"}
    )
    assert list(target.iterdir())
