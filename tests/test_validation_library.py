"""Built-in validation rules, references, uniqueness and machine-readable results."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from undatum.common.errors import ConfigurationError
from undatum.core import app
from undatum.validate.library import RULES, catalogue, get_rule


@pytest.mark.parametrize(
    ("rule", "valid", "invalid", "params"),
    [
        ("email", ["a@example.org"], ["no-at", ""], {}),
        ("url", ["https://example.org/x"], ["example", "http//x"], {}),
        ("date", ["2026-10-08"], ["2026-13-01", "08.10.2026"], {}),
        ("date", ["08.10.2026"], ["2026-10-08"], {"formats": ["%d.%m.%Y"]}),
        ("datetime", ["2026-10-08T10:00:00", "2026-10-08 10:00:00Z"], ["yesterday"], {}),
        ("phone", ["+4930123456", "+1 202 555 0143"], ["12345", "+0123"], {}),
        ("country", ["DE", "deu", "FR"], ["XX", "ZZZ"], {}),
        ("country", ["DE"], ["DEU"], {"alpha": "2"}),
        ("country", ["276"], ["DE"], {"alpha": "numeric"}),
        ("currency", ["EUR", "usd"], ["EURO", "XXZ"], {}),
        ("language", ["en", "en-GB", "ru"], ["english", "zz"], {}),
        (
            "iban",
            ["DE89 3704 0044 0532 0130 00", "GB82WEST12345698765432"],
            ["DE89370400440532013001"],
            {},
        ),
        ("uuid", ["123e4567-e89b-12d3-a456-426614174000"], ["123e4567"], {}),
        ("pattern", ["AB-12"], ["AB-123", "x AB-12"], {"regex": "[A-Z]{2}-[0-9]{2}"}),
        ("integer", ["42", "-7"], ["4.2", "x"], {}),
        ("number", ["4.2", "1e3", "-7"], ["x", "nan"], {}),
        ("boolean", ["true", "No", "1"], ["maybe"], {}),
        ("ru.org.inn", ["7707083893"], ["7707083894"], {}),
    ],
)
def test_rules(rule, valid, invalid, params):
    spec = get_rule(rule)
    for value in valid:
        assert spec.check(value, params), (rule, value)
    for value in invalid:
        assert not spec.check(value, params), (rule, value)


def test_unknown_names_suggest_alternatives():
    with pytest.raises(ConfigurationError) as info:
        get_rule("emial")
    assert "email" in str(info.value)
    assert get_rule("common.email").name == "email"


def test_catalogue_covers_every_rule():
    names = [entry["name"] for entry in catalogue()]
    assert names == list(RULES)
    assert {"date", "phone", "country", "currency", "language", "iban", "uuid", "pattern"} <= set(
        names
    )


# ---------------------------------------------------------------- rule files


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "people.csv").write_text(
        "id,country,email,code\n1,DE,a@x.org,A1\n2,XX,b@x.org,A2\n3,FR,bad,A1\n4,US,c@x.org,A3\n"
    )
    (tmp_path / "ref").mkdir()
    (tmp_path / "ref" / "countries.csv").write_text("code,name\nDE,Germany\nFR,France\nXX,Test\n")
    return tmp_path


def _rules(path, rules):
    path.write_text(json.dumps({"rules": rules}))
    return str(path)


def _validate(*args, code=None):
    result = CliRunner().invoke(app, ["validate", *args])
    if code is not None:
        assert result.exit_code == code, result.output
    return result


def test_country_rule_in_rule_file(data):
    rules = _rules(
        data / "r.json", [{"name": "iso country", "field": "country", "format": "country"}]
    )
    document = json.loads(_validate("people.csv", "--rules", rules, "--json", code=1).stdout)
    assert [(v["row"], v["value"]) for v in document["violations"]] == [(1, "XX")]
    assert document["violations"][0]["rule"] == "iso country"


def test_misspelled_format_is_a_configuration_error(data):
    rules = _rules(data / "r.json", [{"field": "email", "format": "emial"}])
    result = _validate("people.csv", "--rules", rules)
    assert isinstance(result.exception, ConfigurationError)
    assert result.exception.exit_code == 2
    assert "Did you mean email" in str(result.exception)


def test_unknown_rule_type_is_a_configuration_error(data):
    rules = _rules(data / "r.json", [{"field": "email", "type": "emailish"}])
    result = _validate("people.csv", "--rules", rules)
    assert isinstance(result.exception, ConfigurationError)
    assert result.exception.exit_code == 2


def test_references_relative_to_the_rule_file(data):
    rules = _rules(
        data / "ref" / "r.json",
        [{"field": "country", "references": {"file": "countries.csv", "field": "code"}}],
    )
    document = json.loads(_validate("people.csv", "--rules", rules, "--json", code=1).stdout)
    assert [(v["row"], v["value"]) for v in document["violations"]] == [(3, "US")]
    assert "countries.csv:code" in document["violations"][0]["message"]


def test_unique(data):
    rules = _rules(data / "r.json", [{"field": "code", "unique": True, "severity": "warning"}])
    document = json.loads(_validate("people.csv", "--rules", rules, "--json").stdout)
    assert [(v["row"], v["value"]) for v in document["violations"]] == [(2, "A1")]
    assert "first in row 0" in document["violations"][0]["message"]
    # --threads would split the file across processes; unique rules stay in one.
    document = json.loads(
        _validate("people.csv", "--rules", rules, "--json", "--threads", "2").stdout
    )
    assert len(document["violations"]) == 1


def test_jsonl_violations(data):
    rules = _rules(
        data / "r.json",
        [
            {"name": "country", "field": "country", "format": "country"},
            {"name": "mail", "field": "email", "format": "email"},
        ],
    )
    result = _validate("people.csv", "--rules", rules, "-O", "jsonl", code=1)
    lines = [json.loads(line) for line in result.stdout.splitlines()]
    assert [(v["rule"], v["row"]) for v in lines] == [("country", 1), ("mail", 2)]
    for violation in lines:
        assert {"rule", "field", "severity", "row", "value", "message"} <= set(violation)
    assert "2 violations in 4 records" in result.stderr


def test_list_rules():
    result = CliRunner().invoke(app, ["validate", "--list-rules"])
    assert result.exit_code == 0
    for name in ("country", "iban", "phone", "references"):
        assert name in result.stdout
    document = json.loads(CliRunner().invoke(app, ["validate", "--list-rules", "--json"]).stdout)
    assert document["schema"] == "undatum.validate-rules/1"
    assert {r["name"] for r in document["rules"]} == set(RULES)


def test_validate_needs_a_file_without_list_rules():
    assert CliRunner().invoke(app, ["validate"]).exit_code == 2


def test_phone_region_without_extra(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_phonenumbers(name, *args, **kwargs):
        if name == "phonenumbers":
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_phonenumbers)
    from undatum.common.errors import DependencyError

    with pytest.raises(DependencyError):
        get_rule("phone").check("030 123456", {"region": "DE"})
