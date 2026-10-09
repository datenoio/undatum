"""``--where`` and ``--add``: SQL expressions evaluated by DuckDB on typed values."""

from __future__ import annotations

import csv
import json

import pytest
from typer.testing import CliRunner

from undatum.common.errors import ValidationError
from undatum.core import app
from undatum.io import open_source
from undatum.ops import WhereConfig, get_operation, run
from undatum.ops.expr import parse_add

CSV = (
    "id,city,price,qty,day,code\n"
    "1,Berlin,1.50,2,2020-01-02,007\n"
    "2,Paris,2,3,2021-03-04,012\n"
    "3,Rome,n/a,1,2022-05-06,100\n"
)


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "o.csv").write_text(CSV, encoding="utf8")
    rows = [
        {"id": 1, "city": "Berlin", "price": 1.5, "qty": 2, "tags": ["a"]},
        {"id": 2, "city": "Paris", "price": 2, "qty": 3, "tags": []},
    ]
    (tmp_path / "o.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    return tmp_path


def _invoke(*args):
    result = CliRunner().invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.stdout


def _csv_rows(text):
    return list(csv.DictReader(text.splitlines()))


@pytest.mark.parametrize("engine", ["duckdb", "python"])
def test_where_on_typed_values_keeps_original_text(data, engine):
    out = _invoke(
        "select", "o.csv", "--where", "price > 1 AND day >= DATE '2021-01-01'", "-e", engine
    )
    assert _csv_rows(out) == [
        {"id": "2", "city": "Paris", "price": "2", "qty": "3", "day": "2021-03-04", "code": "012"}
    ]


@pytest.mark.parametrize("engine", ["duckdb", "python"])
def test_add_computed_and_replaced_columns(data, engine):
    _invoke(
        "convert",
        "o.csv",
        "out.csv",
        "--add",
        "total = price * qty",
        "--add",
        "city = upper(city)",
        "-e",
        engine,
    )
    rows = _csv_rows((data / "out.csv").read_text())
    assert [r["city"] for r in rows] == ["BERLIN", "PARIS", "ROME"]
    assert [r["total"] for r in rows] == ["3.0", "6.0", ""]  # n/a is NULL
    assert rows[0]["price"] == "1.50" and rows[0]["code"] == "007"  # text kept
    assert list(rows[0]) == ["id", "city", "price", "qty", "day", "code", "total"]


def test_codes_with_leading_zeros_stay_text(data):
    out = _invoke("select", "o.csv", "--where", "code = '007'")
    assert [r["id"] for r in _csv_rows(out)] == ["1"]


def test_json_and_lists(data):
    out = _invoke("select", "o.jsonl", "--where", "len(tags) > 0", "--add", "t = price * qty")
    assert [json.loads(line) for line in out.splitlines()] == [
        {"id": 1, "city": "Berlin", "price": 1.5, "qty": 2, "tags": ["a"], "t": 3.0}
    ]


def test_where_on_other_commands(data):
    assert _invoke("count", "o.csv", "--where", "qty > 1").strip() == "2"
    assert len(_csv_rows(_invoke("head", "o.csv", "--where", "id > 1", "-n", "1"))) == 1
    sampled = _csv_rows(_invoke("sample", "o.csv", "-n", "5", "--where", "city <> 'Paris'"))
    assert {r["city"] for r in sampled} == {"Berlin", "Rome"}
    found = _csv_rows(_invoke("search", "o.csv", "--pattern", "^R", "--where", "id >= 2"))
    assert [r["city"] for r in found] == ["Rome"]


def test_engines_agree_on_dirty_text(tmp_path):
    path = tmp_path / "d.csv"
    path.write_text("a,b\n1,x\n2,\n3,NULL\n4,4.5\n")
    outputs = {}
    for engine in ("duckdb", "python"):
        out = tmp_path / f"{engine}.csv"
        cfg = WhereConfig(where="a >= 2", add=("c = a * 10",))
        run("where", cfg, open_source(str(path)), str(out), engine=engine)
        outputs[engine] = out.read_text()
    assert outputs["duckdb"] == outputs["python"]


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("pricee > 1", "pricee"),
        ("(SELECT 1) = 1", "subqueries"),
        ("getenv('HOME') = ''", "getenv()"),
        ("id > 1; DROP TABLE x", "Invalid --where"),
        ("city > 1", "Text columns"),
    ],
)
def test_invalid_expressions_are_user_errors(data, expression, message):
    result = CliRunner().invoke(app, ["select", "o.csv", "--where", expression])
    assert result.exit_code == 1
    assert isinstance(result.exception, ValidationError)
    assert message in str(result.exception)


def test_unknown_column_suggestions(data):
    with pytest.raises(ValidationError) as info:
        list(get_operation("where").apply(open_source("o.csv"), WhereConfig(where="prise > 1")))
    assert "price" in (info.value.context.get("suggestions") or info.value.message)


def test_parse_add():
    assert parse_add("total = price * qty") == ("total", "price * qty")
    assert parse_add('"unit price" = price / qty') == ("unit price", "price / qty")
    assert parse_add("flag = a == b") == ("flag", "a == b")
    with pytest.raises(ValidationError):
        parse_add("price * qty")
    with pytest.raises(ValidationError):
        parse_add("a == b")


def test_where_agent_tool(data):
    from undatum.tools import schemas
    from undatum.tools.sandbox import configure_sandbox

    configure_sandbox(data)
    try:
        result = schemas.call_tool(
            "where", {"input_path": "o.csv", "where": "qty >= 2", "add": ["t = price * qty"]}
        )
        assert result["ok"], result
        assert [r["t"] for r in result["data"]["records"]] == [3.0, 6.0]
        blocked = schemas.call_tool("where", {"input_path": "o.csv", "add": ["k = getenv('HOME')"]})
        assert not blocked["ok"]
    finally:
        configure_sandbox(allow_anywhere=True)
