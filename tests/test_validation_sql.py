"""Rule files checked by DuckDB give the violations of the Python rules."""

from __future__ import annotations

import json

import pytest
import yaml
from typer.testing import CliRunner

from undatum.common.validation_rules import parse_validation_rules
from undatum.core import app
from undatum.io import RowSource
from undatum.validate.sql import re2_pattern, sql_violations

runner = CliRunner()

# Values that the Python checks read in different ways: numbers in Python's float() grammar
# (underscores, inf, nan, spaces), duplicates, empty fields, non-ASCII text, quotes.
CSV = (
    "id,code,amount,name,status,email\n"
    "1,A1,10,Alice,active,a@x.org\n"
    "2,A2,1_000,Bob,inactive,\n"
    "3,A1, 7.5 ,Élodie,active,c@x.org\n"
    "4,,nan,O'Brien,unknown,d@x.org\n"
    "5,B9,inf,Zoë,active,e@x.org\n"
    '6,A2,-3,"Quote ""x""",active,f@x.org\n'
    "7,C7,abc,,active,g@x.org\n"
    "8,A1,1e3,Ann,pending,h@x.org\n"
    "9,c7,12,Ann,ACTIVE,i@x.org\n"
    "10,A3,0.5,Анна,active,j@x.org\n"
    "11,A4,  ,Long name here,active,k@x.org\n"
)
REFERENCE = "code,label\nA1,one\nA2,two\nA3,three\nB9,nine\n"

RULES = {
    "required": [{"field": "code", "required": True}],
    "type_number": [{"field": "amount", "type": "number"}],
    "type_integer": [{"field": "amount", "data_type": "integer", "type": "field"}],
    "type_float": [{"field": "amount", "type": "float"}],
    "type_boolean": [{"field": "status", "type": "boolean"}],
    "type_string_date": [{"field": "name", "type": "string"}, {"field": "id", "type": "date"}],
    "range": [{"field": "amount", "min": 0, "max": 100}],
    "range_float_bounds": [{"field": "amount", "min": 0.75, "max": 1e3}],
    "length": [{"field": "name", "min_length": 4, "max_length": 6}],
    "enum": [{"field": "status", "enum": ["active", "inactive"]}],
    "enum_numbers": [{"field": "id", "enum": [1, 2, "3"]}],
    "pattern": [{"field": "code", "pattern": "[A-Z]\\d$"}],
    "pattern_class": [{"field": "name", "pattern": "[^a-z]"}],
    "unique": [{"field": "code", "unique": True}],
    "unique_after_type": [{"field": "amount", "type": "number", "unique": True}],
    "references": [{"field": "code", "references": {"file": "ref.csv", "field": "code"}}],
    "unique_and_references": [
        {"field": "code", "unique": True, "references": {"file": "ref.csv", "field": "code"}}
    ],
    "missing_field": [{"field": "nope", "required": True}, {"field": "nope2", "min": 1}],
    "severities": [
        {"name": "code-needed", "field": "code", "required": True, "severity": "warning"},
        {"field": "status", "enum": ["active"], "severity": "info"},
        {"field": "amount", "type": "number", "max": 50},
    ],
    "everything": [
        {
            "field": "code",
            "required": True,
            "unique": True,
            "min_length": 2,
            "pattern": "[A-Z]",
            "enum": ["A1", "A2", "A3", "B9", "C7"],
        }
    ],
}


@pytest.fixture
def data(tmp_path):
    (tmp_path / "data.csv").write_text(CSV, encoding="utf8")
    (tmp_path / "ref.csv").write_text(REFERENCE, encoding="utf8")
    return tmp_path


def _rules(folder, rules):
    path = folder / "rules.yml"
    path.write_text(yaml.safe_dump({"rules": rules}, allow_unicode=True), encoding="utf8")
    return str(path)


def _python(path, rules_file, options=None):
    from undatum.common.filter import match_filter

    rule_set = parse_validation_rules(rules_file)
    violations = []
    total = 0
    filter_expr = (options or {}).get("filter")
    try:
        for index, record in enumerate(RowSource(path, options or {})):
            total += 1
            if filter_expr and not match_filter(record, filter_expr):
                continue
            violations.extend(rule_set.validate_record(record, index))
    finally:
        rule_set.close()
    return total, violations


@pytest.mark.parametrize("name", list(RULES))
def test_same_violations_as_python(data, name):
    rules_file = _rules(data, RULES[name])
    path = str(data / "data.csv")
    checked = sql_violations(path, parse_validation_rules(rules_file))
    assert checked is not None, "the rules should compile"
    assert checked == _python(path, rules_file)


def test_filter(data):
    rules_file = _rules(data, RULES["everything"])
    path = str(data / "data.csv")
    options = {"filter": "status == 'active'"}
    checked = sql_violations(path, parse_validation_rules(rules_file), options)
    assert checked is not None
    assert checked == _python(path, rules_file, options)


@pytest.mark.parametrize(
    "rules",
    [
        [{"field": "email", "format": "email"}],
        [{"field": "code", "custom": "common.email"}],
        [{"type": "cross-field", "fields": ["id"], "condition": "id != ''"}],
        [{"field": "name", "pattern": "\\w+"}],
        [{"field": "name", "pattern": "(?<=A)nn"}],
        [{"field": "amount", "max": float("inf")}],
    ],
    ids=["format", "custom", "cross-field", "unicode-class", "re2-unsupported", "infinite-bound"],
)
def test_python_checks_rules_that_do_not_compile(data, rules):
    rules_file = _rules(data, rules)
    assert sql_violations(str(data / "data.csv"), parse_validation_rules(rules_file)) is None


def test_numbers_only_python_reads_use_python(tmp_path):
    (tmp_path / "data.csv").write_text("amount\n١٢\n5\n", encoding="utf8")
    rules_file = _rules(tmp_path, [{"field": "amount", "max": 10}])
    assert sql_violations(str(tmp_path / "data.csv"), parse_validation_rules(rules_file)) is None


def test_json_input_uses_python(tmp_path):
    (tmp_path / "data.jsonl").write_text('{"a": 1}\n', encoding="utf8")
    rules_file = _rules(tmp_path, [{"field": "a", "required": True}])
    assert sql_violations(str(tmp_path / "data.jsonl"), parse_validation_rules(rules_file)) is None


@pytest.mark.parametrize(
    "pattern,expected",
    [
        ("[A-Z]\\d$", "^(?:[A-Z]\\p{Nd}(?:\\n?\\z))"),
        ("[]$]x", "^(?:[]$]x)"),
        ("a\\Z", "^(?:a\\z)"),
        ("\\w+", None),
        ("a\\b", None),
    ],
)
def test_re2_pattern(pattern, expected):
    assert re2_pattern(pattern) == expected


@pytest.mark.parametrize("output_format", ["json", "jsonl"])
def test_cli_engines_agree(data, output_format):
    rules_file = _rules(data, RULES["severities"])
    outputs = {}
    for engine in ("python", "duckdb"):
        result = runner.invoke(
            app,
            [
                "validate",
                str(data / "data.csv"),
                "--rules",
                rules_file,
                "--engine",
                engine,
                "--output-format",
                output_format,
            ],
        )
        outputs[engine] = result.output
    assert outputs["duckdb"] == outputs["python"]
    if output_format == "json":
        document = json.JSONDecoder().raw_decode(outputs["duckdb"])[0]  # stderr follows
        assert document["statistics"]["total_records"] == 11


def test_quality_uses_the_same_violations(data):
    from undatum.cmds.quality import _violations

    rules_file = _rules(data, RULES["severities"])
    path = str(data / "data.csv")
    _, python_violations = _python(path, rules_file)
    severities, sample, by_rule = _violations(path, rules_file, {})
    assert sum(severities.values()) == len(python_violations)
    assert sample == python_violations[: len(sample)]
