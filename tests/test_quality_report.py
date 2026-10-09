"""``undatum quality``: profile, schema, rules, thresholds and a CI exit code."""

from __future__ import annotations

import csv
import json

import pytest
from typer.testing import CliRunner

from undatum.common.errors import ConfigurationError
from undatum.common.results import SCHEMAS
from undatum.core import app


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with open("data.csv", "w", newline="", encoding="utf8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "email", "amount", "country"])
        for i in range(100):
            email = "" if i % 20 == 0 else f"u{i}@x.org"  # 5% empty
            amount = "abc" if i == 9 else ("n/a" if i == 7 else i * 3)
            writer.writerow([i, email, amount, "XX" if i == 5 else "DE"])
    (tmp_path / "rules.yml").write_text(
        "rules:\n  - name: iso country\n    field: country\n    format: country\n"
    )
    return tmp_path


def _run(*args):
    return CliRunner().invoke(app, ["quality", *args])


def _json(*args):
    result = _run(*args, "--json")
    return result, json.loads(result.stdout)


def test_json_report_measures_fields(data):
    result, report = _json("data.csv")
    assert result.exit_code == 0
    assert report["schema"] == "undatum.quality/1"
    assert set(report) >= {"summary", "fields", "schema_check", "violations", "verdict"}
    assert report["summary"]["rows"] == 100
    fields = {f["name"]: f for f in report["fields"]}
    assert fields["email"]["null_rate"] == 0.05
    assert fields["id"]["distinct"] == 100 and fields["id"]["type"] == "integer"
    assert fields["amount"]["type"] == "integer"
    assert fields["amount"]["nulls"] == 1  # n/a counts as empty
    assert fields["amount"]["conformance"] == pytest.approx(98 / 99, abs=1e-6)  # "abc"
    assert fields["country"]["top_values"][0] == {"value": "DE", "count": 99}
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(report, SCHEMAS["undatum.quality/1"].json_schema())


def test_null_rate_threshold_fails_with_exit_1(data):
    (data / "q.yml").write_text("max_null_rate:\n  email: 0.01\n")
    result, report = _json("data.csv", "--thresholds", "q.yml")
    assert result.exit_code == 1
    check = report["verdict"]["checks"][0]
    assert (check["target"], check["value"], check["passed"]) == ("email", 0.05, False)
    assert report["verdict"]["passed"] is False


def test_thresholds_that_pass(data):
    (data / "q.yml").write_text(
        "min_rows: 50\nmax_null_rate:\n  '*': 0.1\nmin_type_conformance:\n  amount: 0.95\n"
        "max_error_violations: 1\n"
    )
    result, report = _json("data.csv", "--thresholds", "q.yml", "--rules", "rules.yml")
    assert result.exit_code == 0, report["verdict"]
    assert report["violations"]["by_severity"]["error"] == 1
    assert report["violations"]["sample"][0]["row"] == 5
    assert len(report["verdict"]["checks"]) == 1 + 4 + 1 + 1  # rows, 4 fields, conformance, errors


def test_schema_contract(data):
    (data / "expected.json").write_text(
        json.dumps(
            {"fields": [{"name": "id", "type": "integer"}, {"name": "email", "type": "string"}]}
        )
    )
    (data / "strict.yml").write_text("schema: strict\n")
    (data / "additive.yml").write_text("schema: additive\n")
    result, report = _json("data.csv", "--schema", "expected.json", "--thresholds", "strict.yml")
    assert result.exit_code == 1  # amount and country were added
    assert {c["field"] for c in report["schema_check"]["changes"]} == {"amount", "country"}
    result, _ = _json("data.csv", "--schema", "expected.json", "--thresholds", "additive.yml")
    assert result.exit_code == 0


def test_html_report(data):
    result = _run("data.csv", "--rules", "rules.yml", "-o", "report.html")
    assert result.exit_code == 0
    page = (data / "report.html").read_text()
    assert page.startswith("<!doctype html>")
    for text in (
        "100 records",
        "Type conformance",
        "Rule violations",
        "1 error",
        "<code>email</code>",
    ):
        assert text in page
    assert "<script" not in page and "http" not in page.split("<body>")[1]


def test_markdown_is_the_default(data):
    result = _run("data.csv")
    assert result.stdout.startswith("# Data quality: `data.csv`")
    assert "| `email` | string | 5.0% |" in result.stdout


def test_bad_thresholds_are_configuration_errors(data):
    (data / "q.yml").write_text("max_null_rates: 0.1\n")
    result = _run("data.csv", "--thresholds", "q.yml")
    assert isinstance(result.exception, ConfigurationError)
    assert result.exception.exit_code == 2
    assert "max_null_rate" in str(result.exception)
    (data / "q.yml").write_text("max_null_rate: 3\n")
    assert isinstance(_run("data.csv", "--thresholds", "q.yml").exception, ConfigurationError)


def test_missing_field_in_thresholds_fails(data):
    (data / "q.yml").write_text("max_null_rate:\n  phone: 0.1\n")
    result, report = _json("data.csv", "--thresholds", "q.yml")
    assert result.exit_code == 1
    assert "not found" in report["verdict"]["checks"][0]["message"]


def test_formats_duckdb_cannot_read(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(["id", "city"])
    for i, city in enumerate(["Berlin", None, "Paris", "Berlin"]):
        sheet.append([i, city])
    book.save(tmp_path / "w.xlsx")
    result = CliRunner().invoke(app, ["quality", str(tmp_path / "w.xlsx"), "--json"])
    report = json.loads(result.stdout)
    fields = {f["name"]: f for f in report["fields"]}
    assert report["summary"]["rows"] == 4
    assert fields["city"]["null_rate"] == 0.25
    assert fields["id"]["type"] == "integer"


def test_sdk_and_pipeline(data):
    from undatum.common.pipeline_parser import PipelineSpec, validate_pipeline
    from undatum.sdk import Dataset

    report = Dataset.read("data.csv").quality(rules="rules.yml")
    assert report["summary"]["violations"]["error"] == 1
    spec = PipelineSpec([{"name": "q", "command": "quality", "args": {"input": "data.csv"}}])
    assert validate_pipeline(spec) == []
