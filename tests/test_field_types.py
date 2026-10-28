"""The shared field-type rules, and that every command reports the same types."""

from __future__ import annotations

import csv
import json

import duckdb
import pytest
from typer.testing import CliRunner

from undatum.common.field_types import column_types, infer_value_types, normalize_type
from undatum.core import app

runner = CliRunner()


def _types(columns: dict[str, list[str]], **kwargs) -> dict[str, str]:
    import pyarrow as pa

    conn = duckdb.connect()
    conn.register(
        "t", pa.table({name: pa.array(values, pa.string()) for name, values in columns.items()})
    )
    return column_types(conn, "t", text_values=True, **kwargs)


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["1", "2", "-3"], "integer"),
        (["1.5", "2", "3e2"], "number"),
        (["true", "False", "TRUE"], "boolean"),
        (["2020-01-02", "2021-12-31"], "date"),
        (["31.12.2020", "01.02.2021"], "date"),
        (["31/12/2020", "2020/12/31"], "date"),
        (["2020-01-02T10:00:00", "2020-01-02 11:30:00"], "datetime"),
        (["007", "012", "100"], "string"),
        (["alpha", "beta"], "string"),
        (["", "n/a", "-"], "null"),
        (["1", "2", "n/a", "", "NULL"], "integer"),
    ],
)
def test_text_rules(values, expected):
    assert _types({"c": values})["c"] == expected


def test_a_few_bad_values_do_not_make_a_string():
    values = [str(i) for i in range(99)] + ["abc"]
    assert _types({"c": values})["c"] == "integer"
    assert _types({"c": values[:90] + ["abc"] * 10})["c"] == "string"


def test_digit_codes_are_reported():
    codes: set[str] = set()
    assert _types({"zip": ["01234", "99999"], "n": ["1", "2"]}, codes=codes)["zip"] == "string"
    assert codes == {"zip"}


def test_typed_columns_keep_their_type():
    conn = duckdb.connect()
    relation = "(SELECT '2005' AS year, 1.5 AS price, {'name': 'A'} AS who)"
    assert column_types(conn, relation, text_values=False) == {
        "year": "string",
        "price": "number",
        "who": "object",
        "who.name": "string",
    }


def test_value_counts_use_the_same_rules():
    types = infer_value_types({"n": {"1": 30, "2": 5, "x": 1}, "d": {"31.12.2020": 3}})
    assert types == {"n": "integer", "d": "date"}


STATS_NAMES = {"int": "integer", "float": "number", "bool": "boolean", "date": "date"}
STATS_NAMES.update({"datetime": "datetime", "str": "string", "numstr": "string"})


def test_commands_report_the_same_types(tmp_path):
    rows = [
        {
            "id": str(i + 1),
            "amount": f"{i}.5" if i % 2 else str(i),
            "code": f"{i % 50:03d}",
            "flag": "true" if i % 3 else "false",
            "day": f"{i % 28 + 1:02d}.{i % 12 + 1:02d}.2020",
            "at": f"2020-01-{i % 28 + 1:02d}T10:00:00",
            "note": "n/a" if i % 10 == 0 else ("abc" if i == 7 else str(i)),
            "name": "alpha" if i % 2 else "beta",
        }
        for i in range(300)
    ]
    source = tmp_path / "types.csv"
    with open(source, "w", newline="", encoding="utf8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    def run(*args):
        result = runner.invoke(app, [*args])
        assert result.exit_code == 0, result.output
        return json.loads(result.stdout)

    schema = {
        f["name"]: normalize_type(f["ftype"])
        for f in run("schema", str(source), "--json")["fields"]
    }
    stats = {
        k: STATS_NAMES[v] for k, v in run("stats", str(source), "-O", "json")["fieldtypes"].items()
    }
    quality = {f["name"]: f["type"] for f in run("quality", str(source), "--json")["fields"]}
    from undatum.cmds.drift import profile_file

    drift = {name: info.type for name, info in profile_file(str(source)).items()}
    expected = {
        "id": "integer",
        "amount": "number",
        "code": "string",
        "flag": "boolean",
        "day": "date",
        "at": "datetime",
        "note": "integer",
        "name": "string",
    }
    assert schema == expected
    assert stats == expected
    assert quality == expected
    assert drift == expected
