"""ODCS data contracts: rules and checks read from a contract, and contracts written by schema."""

from __future__ import annotations

import json

import pytest
import yaml
from typer.testing import CliRunner

from undatum.common.errors import ConfigurationError
from undatum.common.results import VALIDATE
from undatum.common.validation_rules import parse_validation_rules
from undatum.core import app
from undatum.validate.odcs import ContractCheck, evaluate_checks, logical_type, read_contract

runner = CliRunner()

CSV = (
    "id,name,email,age,status,city,code\n"
    "1,Alice,alice@example.org,34,active,Berlin,A-1\n"
    "2,Bob,bob@example.org,28,inactive,Paris,B-2\n"
    "3,Carol,not-an-email,45,active,Berlin,c3\n"
    "4,Dave,,23,pending,,D-4\n"
    "5,Eve,eve@example.org,50,active,Rome,E-5\n"
)


def _contract(properties, quality=None, objects=None):
    obj = {"name": "people", "physicalName": "data.csv", "properties": properties}
    if quality:
        obj["quality"] = quality
    return {
        "apiVersion": "v3.2.0",
        "kind": "DataContract",
        "id": "people-contract",
        "version": "1.0.0",
        "schema": objects or [obj],
    }


@pytest.fixture
def data(tmp_path):
    (tmp_path / "data.csv").write_text(CSV, encoding="utf8")
    return tmp_path


def _write(folder, contract, name="contract.odcs.yaml"):
    path = folder / name
    path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf8")
    return str(path)


def _validate(path, rules, *args):
    return runner.invoke(
        app, ["validate", str(path), "--rules", rules, "--format-out", "json", *args]
    )


def _document(result):
    return json.JSONDecoder().raw_decode(result.stdout)[0]


# --------------------------------------------------------------------------- mapping


def test_property_constraints_become_rules():
    contract = read_contract(
        _contract(
            [
                {"name": "id", "logicalType": "integer", "primaryKey": True},
                {
                    "name": "name",
                    "physicalName": "full_name",
                    "logicalType": "string",
                    "required": True,
                    "logicalTypeOptions": {"minLength": 2, "maxLength": 9, "pattern": "[a-z]"},
                },
                {
                    "name": "email",
                    "logicalType": "string",
                    "logicalTypeOptions": {"format": "email"},
                },
                {"name": "age", "logicalType": "number", "logicalTypeOptions": {"minimum": 0}},
                {"name": "active", "logicalType": "boolean"},
                {"name": "day", "logicalType": "date"},
                {"name": "at", "logicalType": "timestamp"},
                {"name": "level", "enum": [{"value": 1}, {"value": "high"}, {"value": True}]},
                {"name": "anything", "logicalType": "string"},
            ]
        )
    )
    rules = {rule["field"]: rule for rule in contract.rules}
    assert rules["id"] == {
        "field": "id",
        "name": "id",
        "required": True,
        "unique": True,
        "type": "integer",
    }
    assert rules["full_name"]["min_length"] == 2 and rules["full_name"]["max_length"] == 9
    assert rules["full_name"]["pattern"] == "(?s:.*?)(?:[a-z])"
    assert rules["email"]["format"] == "email"
    assert rules["age"] == {"field": "age", "name": "age", "type": "number", "min": 0}
    assert rules["active"]["format"] == "boolean"
    assert rules["day"]["format"] == "date"
    assert rules["at"]["format"] == "datetime"
    assert rules["level"]["enum"] == [1, "1", "high", True, "true", "True"]
    assert "anything" not in rules
    assert contract.checks == [] and contract.not_checked == []


def test_checks_and_not_checked():
    contract = read_contract(
        _contract(
            [
                {"name": "a", "primaryKey": True, "primaryKeyPosition": 2},
                {"name": "b", "primaryKey": True, "primaryKeyPosition": 1},
                {
                    "name": "n",
                    "logicalType": "integer",
                    "logicalTypeOptions": {"exclusiveMinimum": 0, "multipleOf": 5},
                    "quality": [
                        {"metric": "nullValues", "mustBeLessThan": 5, "unit": "percent"},
                        {"rule": "duplicateCheck", "mustBe": 0, "severity": "warning"},
                        {"type": "sql", "query": "SELECT 1", "mustBe": 1},
                        {"type": "custom", "engine": "soda"},
                        {"metric": "nullValues"},
                    ],
                },
                {"name": "t", "logicalType": "time"},
                {"name": "s", "logicalType": "string", "logicalTypeOptions": {"format": "ipv4"}},
            ],
            quality=[
                {"metric": "rowCount", "mustBeGreaterThan": 0},
                {"metric": "duplicateValues", "arguments": {"properties": ["a", "n"]}, "mustBe": 0},
                {"metric": "nullValues", "mustBe": 0},
                {"type": "text", "description": "People."},
            ],
        )
    )
    rules = {rule["field"]: rule for rule in contract.rules}
    assert rules["a"] == {"field": "a", "name": "a", "required": True}
    summary = [(c.name, c.metric, c.fields, c.operator, c.limit) for c in contract.checks]
    assert summary == [
        ("n exclusiveMinimum 0", "invalidValues", ("n",), "mustBe", 0),
        ("n multipleOf 5", "invalidValues", ("n",), "mustBe", 0),
        ("n nullValues", "nullValues", ("n",), "mustBeLessThan", 5),
        ("n duplicateCheck", "duplicateValues", ("n",), "mustBe", 0),
        ("primary key (b, a)", "duplicateValues", ("b", "a"), "mustBe", 0),
        ("people rowCount", "rowCount", (), "mustBeGreaterThan", 0),
        ("people duplicateValues", "duplicateValues", ("a", "n"), "mustBe", 0),
    ]
    assert contract.checks[2].unit == "percent" and contract.checks[3].severity == "warning"
    reasons = {item["name"]: item["reason"] for item in contract.not_checked}
    assert reasons["n sql"] == "SQL checks are not run"
    assert reasons["n custom"].startswith("custom")
    assert reasons["n nullValues"].startswith("needs exactly one operator")
    assert reasons["t"] == "logicalType 'time' is not checked"
    assert reasons["s"] == "logicalTypeOptions.format is not checked"
    assert reasons["people nullValues"] == "nullValues needs a property"
    assert reasons["people text"].startswith("text checks")


def test_schema_object_selection(tmp_path):
    objects = [{"name": "people", "properties": []}, {"name": "orders", "properties": []}]
    path = _write(tmp_path, _contract([], objects=objects))
    with pytest.raises(ConfigurationError, match=r"several schema objects \(people, orders\)"):
        parse_validation_rules(path)
    assert parse_validation_rules(path + "#orders").contract.object_name == "orders"
    with pytest.raises(ConfigurationError, match="no schema object 'nope'"):
        parse_validation_rules(path + "#nope")


# --------------------------------------------------------------------------- checks


def _check(metric, fields=("v",), operator="mustBe", limit=0, **kwargs):
    return ContractCheck(f"{metric}", metric, fields, operator, limit, **kwargs)


RECORDS = [{"v": "a", "w": 1}, {"v": ""}, {"v": None}, {"v": "N/A"}, {"v": "a"}, {"v": "b2"}]


@pytest.mark.parametrize(
    "check,value",
    [
        (_check("nullValues"), 2),
        (_check("missingValues", arguments={"missingValues": ["N/A", None]}), 3),
        (_check("invalidValues", arguments={"validValues": ["a", "b2"]}), 1),
        (_check("invalidValues", arguments={"pattern": r"\d"}), 3),
        (_check("duplicateValues"), 1),
        (_check("duplicateValues", fields=("v", "w")), 0),
        (_check("rowCount", fields=()), 6),
        (_check("nullValues", unit="percent"), round(200 / 6, 6)),
    ],
)
def test_metrics(check, value):
    assert evaluate_checks([check], RECORDS)[0]["value"] == value


def test_numeric_options():
    records = [{"n": value} for value in ("0", "5", "7", "10", "x", "")]
    checks = [
        _check("invalidValues", ("n",), arguments={"exclusiveMinimum": 0}),
        _check("invalidValues", ("n",), arguments={"exclusiveMaximum": 10}),
        _check("invalidValues", ("n",), arguments={"multipleOf": 5}),
    ]
    assert [r["value"] for r in evaluate_checks(checks, records)] == [1, 1, 1]


@pytest.mark.parametrize(
    "operator,limit,passed",
    [
        ("mustBe", 2, True),
        ("mustNotBe", 2, False),
        ("mustBeGreaterThan", 1, True),
        ("mustBeGreaterOrEqualTo", 3, False),
        ("mustBeLessThan", 3, True),
        ("mustBeLessOrEqualTo", 1, False),
        ("mustBeBetween", [2, 4], True),
        ("mustNotBeBetween", [2, 4], False),
    ],
)
def test_operators(operator, limit, passed):
    result = evaluate_checks([_check("nullValues", operator=operator, limit=limit)], RECORDS)[0]
    assert result["passed"] is passed


# --------------------------------------------------------------------------- command


CONTRACT = _contract(
    [
        {"name": "id", "logicalType": "integer", "primaryKey": True},
        {"name": "name", "logicalType": "string", "required": True},
        {"name": "age", "logicalType": "integer", "logicalTypeOptions": {"minimum": 25}},
        {"name": "status", "enum": [{"value": "active"}, {"value": "inactive"}]},
        {
            "name": "email",
            "quality": [{"metric": "nullValues", "mustBe": 0, "severity": "warning"}],
        },
    ],
    quality=[{"metric": "rowCount", "mustBeGreaterOrEqualTo": 5}, {"type": "sql", "query": "x"}],
)


def test_validate_report(data):
    result = _validate(data / "data.csv", _write(data, CONTRACT))
    assert result.exit_code == 1  # record violations of severity error
    document = _document(result)
    assert set(document) <= {"schema", *VALIDATE.properties}
    assert document["statistics"]["errors"] == 2
    assert document["statistics"]["failed_checks"] == {"error": 0, "warning": 1, "info": 0}
    checks = {check["name"]: check for check in document["contract"]["checks"]}
    assert checks["email nullValues"]["value"] == 1
    assert checks["email nullValues"]["passed"] is False
    assert checks["people rowCount"]["passed"] is True
    assert document["contract"]["not_checked"] == [
        {"name": "people sql", "reason": "SQL checks are not run"}
    ]


@pytest.mark.parametrize("severity,code", [("warning", 0), ("error", 1)])
def test_failed_check_exit_code(data, severity, code):
    contract = _contract(
        [
            {
                "name": "email",
                "quality": [{"metric": "nullValues", "mustBe": 0, "severity": severity}],
            }
        ]
    )
    result = _validate(data / "data.csv", _write(data, contract))
    assert result.exit_code == code
    if severity == "warning":
        assert (
            _validate(data / "data.csv", _write(data, contract), "--fail-on-warnings").exit_code
            == 1
        )


def test_text_report(data):
    rules = _write(data, CONTRACT)
    result = runner.invoke(app, ["validate", str(data / "data.csv"), "--rules", rules])
    assert "Contract checks (people)" in result.stdout
    assert "Not checked: people sql: SQL checks are not run" in result.stdout


def test_engines_agree(data):
    contract = _contract(
        [
            {"name": "id", "logicalType": "integer", "primaryKey": True},
            {"name": "name", "required": True, "logicalTypeOptions": {}, "logicalType": "string"},
            {"name": "age", "logicalType": "integer", "logicalTypeOptions": {"maximum": 45}},
            {"name": "status", "enum": [{"value": "active"}, {"value": "inactive"}]},
            {"name": "code", "logicalType": "string", "logicalTypeOptions": {"pattern": "^[A-Z]-"}},
        ]
    )
    rules = _write(data, contract)
    outputs = {
        engine: _validate(data / "data.csv", rules, "--engine", engine).stdout
        for engine in ("python", "duckdb")
    }
    assert outputs["duckdb"] == outputs["python"]
    assert _document_text(outputs["python"])["statistics"]["errors"] == 3


def _document_text(text):
    return json.JSONDecoder().raw_decode(text)[0]


# --------------------------------------------------------------------------- export


def test_export_round_trip(data):
    result = runner.invoke(app, ["schema", str(data / "data.csv"), "--format", "odcs"])
    assert result.exit_code == 0, result.output
    contract = yaml.safe_load(result.stdout)
    assert contract["apiVersion"] == "v3.2.0" and contract["kind"] == "DataContract"
    assert contract["id"] and contract["version"] == "1.0.0" and contract["status"] == "draft"
    (obj,) = contract["schema"]
    assert obj["name"] == "data" and obj["physicalName"] == "data.csv"
    types = {prop["name"]: prop["logicalType"] for prop in obj["properties"]}
    assert types["id"] == "integer" and types["name"] == "string"
    validated = _validate(data / "data.csv", _write(data, contract))
    assert validated.exit_code == 0, validated.output
    assert _document(validated)["statistics"]["total_violations"] == 0


@pytest.mark.parametrize(
    "physical,logical",
    [
        ("BIGINT", "integer"),
        ("DOUBLE", "number"),
        ("DECIMAL(10,2)", "number"),
        ("BOOLEAN", "boolean"),
        ("DATE", "date"),
        ("TIMESTAMP WITH TIME ZONE", "timestamp"),
        ("TIME", "time"),
        ("VARCHAR", "string"),
        ("VARCHAR[]", "array"),
        ("STRUCT(a INTEGER)", "object"),
        ("MAP(VARCHAR, INTEGER)", "map"),
    ],
)
def test_logical_types(physical, logical):
    assert logical_type(physical) == logical
