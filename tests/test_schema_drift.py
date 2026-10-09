"""Schema diff (``diff --schema``) and drift (``schema-drift``) detection."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from undatum.cmds.drift import (
    FieldInfo,
    compare,
    load_schema,
    normalize_type,
    parse_fail_on,
    profile_file,
)
from undatum.common.errors import ValidationError
from undatum.core import app


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "old.csv").write_text("id,amount,city,email\n1,10,Berlin,a@x\n2,20,Paris,b@x\n")
    (tmp_path / "new.csv").write_text(
        "id,amount,town,email,extra\n1,ten,Berlin,a@x,1\n2,20,Paris,,2\n"
    )
    (tmp_path / "same.csv").write_text("id,amount,city,email\n3,30,Rome,c@x\n")
    (tmp_path / "less.csv").write_text("id,amount,city\n4,40,Oslo\n")
    return tmp_path


def _run(*args, code=0):
    result = CliRunner().invoke(app, list(args))
    assert result.exit_code == code, result.output
    return result


def test_profile_types_and_nullability(files):
    fields = profile_file("new.csv")
    assert fields["id"].type == "integer"
    assert fields["amount"].type == "string"  # "ten" is not a number
    assert fields["email"].nullable is True
    assert fields["extra"].type == "integer"


def test_compare_categories_and_rename(files):
    diff = compare(profile_file("old.csv"), profile_file("new.csv"), "old.csv", "new.csv")
    kinds = {(c.kind, c.field) for c in diff.changes}
    assert ("type", "amount") in kinds
    assert ("added", "extra") in kinds and ("added", "town") in kinds
    assert ("removed", "city") in kinds
    assert ("nullability", "email") in kinds
    amount = next(c for c in diff.changes if c.field == "amount")
    assert (amount.old, amount.new) == ("integer", "string")
    assert [(r.old, r.new) for r in diff.renames] == [("city", "town")]
    assert diff.renames[0].value_overlap == 1.0
    assert diff.summary() == {"added": 2, "removed": 1, "type": 1, "nullability": 1}


def test_diff_schema_cli_and_fail_on(files):
    result = _run("diff", "--schema", "old.csv", "new.csv")
    assert "amount: integer -> string" in result.stdout
    assert "city -> town looks like a rename" in result.stdout
    _run("diff", "--schema", "old.csv", "new.csv", "--fail-on", "type", code=1)
    _run("diff", "--schema", "old.csv", "same.csv", "--fail-on", "any")


def test_schema_diff_spelling(files):
    result = _run("schema", "diff", "old.csv", "new.csv", "--json")
    document = json.loads(result.stdout)
    assert document["schema"] == "undatum.schema-diff/1"
    assert document["summary"]["type"] == 1


def test_drift_against_first_file(files):
    result = _run(
        "schema", "drift", "old.csv", "same.csv", "less.csv", "--fail-on", "removed", code=1
    )
    assert "Baseline: old.csv" in result.stdout
    assert "same.csv: no schema changes" in result.stdout
    assert "- email (string)" in result.stdout


def test_drift_with_declared_baseline(files):
    schema = json.loads(_run("schema", "old.csv", "--json").stdout)
    (files / "schema.json").write_text(json.dumps(schema))
    document = json.loads(
        _run("schema-drift", "same.csv", "less.csv", "--baseline", "schema.json", "--json").stdout
    )
    assert document["schema"] == "undatum.schema-drift/1"
    assert document["summary"] == {"files": 2, "drifted": 1}
    less = next(f for f in document["files"] if f["file"] == "less.csv")
    assert less["changes"] == [{"kind": "removed", "field": "email", "old": "string", "new": None}]


def test_json_schema_and_frictionless_baselines(tmp_path):
    json_schema = tmp_path / "s.json"
    json_schema.write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "day": {"type": "string", "format": "date"},
                    "note": {"type": ["string", "null"]},
                },
                "required": ["id", "day"],
            }
        )
    )
    fields = load_schema(str(json_schema))
    assert (fields["id"].type, fields["id"].nullable) == ("integer", False)
    assert fields["day"].type == "date"
    assert fields["note"].nullable is True
    frictionless = tmp_path / "f.json"
    frictionless.write_text(
        json.dumps({"fields": [{"name": "a", "type": "number", "constraints": {"required": True}}]})
    )
    assert load_schema(str(frictionless))["a"] == FieldInfo("a", "number", False)


def test_markdown_report(files):
    _run("schema-drift", "old.csv", "new.csv", "-O", "markdown", "-o", "drift.md")
    text = (files / "drift.md").read_text()
    assert text.startswith("# Schema drift")
    assert "| type | `amount` | integer | string |" in text


def test_directories_and_globs(files):
    (files / "deliveries").mkdir()
    for name in ("old.csv", "same.csv"):
        (files / "deliveries" / name).write_text((files / name).read_text())
    result = _run("schema-drift", "deliveries")
    assert "no schema changes" in result.stdout
    result = _run("schema-drift", "*.csv", "--baseline", "old.csv", "--json")
    assert json.loads(result.stdout)["summary"]["files"] == 3


def test_validation():
    assert parse_fail_on("removed, type") == {"removed", "type"}
    with pytest.raises(ValidationError):
        parse_fail_on("removed,typo")
    assert normalize_type("BIGINT") == "integer"
    assert normalize_type("VARCHAR[]") == "array"
    assert normalize_type("STRUCT(a INTEGER)") == "object"
    assert normalize_type("TIMESTAMP WITH TIME ZONE") == "datetime"
    assert normalize_type("date-time") == "datetime"
