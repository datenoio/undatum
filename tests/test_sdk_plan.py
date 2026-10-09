"""The SDK Dataset is a lazy plan over the operation registry."""

from __future__ import annotations

import datetime
import decimal
import json
import logging

import pandas as pd
import pytest

from undatum import Dataset


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("id,name,age\n1,Alice,34\n2,,28\n2,,28\n3,Carol,45\n", encoding="utf8")
    return path


def test_building_a_chain_reads_nothing(tmp_path, monkeypatch):
    opened = []
    import undatum.io.source as source_module

    original = source_module.RowSource.__iter__

    def tracking(self):
        opened.append(self.path)
        return original(self)

    monkeypatch.setattr(source_module.RowSource, "__iter__", tracking)
    path = tmp_path / "x.csv"
    path.write_text("a\n1\n", encoding="utf8")
    plan = Dataset.read(str(path)).fill("a", value="0").dedup().rename({"a": "b"})
    assert opened == []
    assert [step.name for step in plan.steps] == ["fill", "dedup", "rename"]
    assert list(plan) == [{"b": "1"}]
    assert opened == [str(path)]


def test_steps_do_not_write_intermediate_files(csv_file, tmp_path, monkeypatch):
    import tempfile

    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    out = tmp_path / "out.jsonl"
    Dataset.read(str(csv_file)).rename({"name": "who"}).fill("who", value="?").dedup().write(
        str(out)
    )
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert rows == [
        {"id": "1", "who": "Alice", "age": "34"},
        {"id": "2", "who": "?", "age": "28"},
        {"id": "3", "who": "Carol", "age": "45"},
    ]
    assert list(scratch.iterdir()) == []


def test_typed_values_survive_a_chain(tmp_path):
    path = tmp_path / "typed.parquet"
    pd.DataFrame(
        {
            "day": [datetime.date(2024, 1, 2), datetime.date(2023, 5, 6)],
            "price": [decimal.Decimal("1.50"), decimal.Decimal("2.25")],
            "n": [2, 1],
        }
    ).to_parquet(path, index=False)
    rows = list(Dataset.read(str(path)).rename({"n": "rank"}).sort("rank"))
    assert [r["rank"] for r in rows] == [1, 2]
    assert isinstance(rows[0]["day"], datetime.date)
    assert rows[0]["day"] == datetime.date(2023, 5, 6)
    assert isinstance(rows[0]["price"], decimal.Decimal)


def test_nested_values_survive_from_records():
    records = [{"user": {"name": "a"}, "tags": ["x"]}, {"user": {"name": "b"}, "tags": []}]
    rows = Dataset.from_records(records).enum("i").collect()
    assert rows[1] == {"user": {"name": "b"}, "tags": [], "i": 2}


def test_write_runs_sql_plan_when_every_step_has_one(csv_file, tmp_path, caplog):
    out = tmp_path / "out.csv"
    with caplog.at_level(logging.DEBUG, logger="undatum.sdk.dataset"):
        Dataset.read(str(csv_file)).rename({"name": "who"}).limit(2).write(str(out))
    assert any("DuckDB plan" in message for message in caplog.messages)
    assert out.read_text().splitlines() == ["id,who,age", "1,Alice,34", "2,,28"]


def test_sql_and_python_plans_agree(csv_file, tmp_path):
    plan = Dataset.read(str(csv_file)).fill("name", value="-").select(["id", "name"]).slice(1, 3)
    sql_out = tmp_path / "sql.csv"
    plan.write(str(sql_out))
    assert sql_out.read_text().splitlines() == ["id,name", "2,-", "2,-"]
    assert plan.collect() == [{"id": "2", "name": "-"}, {"id": "2", "name": "-"}]


def test_query_methods(csv_file):
    ds = Dataset.read(str(csv_file))
    assert ds.count() == 4
    assert ds.uniq("id") == [{"id": "1"}, {"id": "2"}, {"id": "3"}]
    assert ds.frequency("id")[0] == {"id": "2", "count": 2}
    assert ds.filter(query="age > 30").count() == 2
    assert ds.filter(pattern="^Al", fields=["name"]).collect()[0]["name"] == "Alice"
    schema = ds.schema()
    assert set(schema) == {"id", "name", "age"}


def test_validate(csv_file):
    report = Dataset.read(str(csv_file)).validate(
        [{"field": "name", "required": True, "severity": "error"}]
    )
    assert report["records"] == 4
    assert report["valid"] == 2
    assert {v["row"] for v in report["violations"]} == {1, 2}


def test_join_exclude_concat(tmp_path):
    left = Dataset.from_records([{"id": 1, "a": "x"}, {"id": 2, "a": "y"}])
    right = Dataset.from_records([{"id": 2, "b": "z"}])
    assert left.join(right, "id").collect() == [{"id": 2, "a": "y", "b": "z"}]
    assert left.exclude(right, on="id").collect() == [{"id": 1, "a": "x"}]
    assert left.concat(right).count() == 3


def test_stats_on_a_plan_cleans_up(csv_file, tmp_path, monkeypatch):
    import tempfile

    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    stats = Dataset.read(str(csv_file)).dedup().stats()
    assert stats.count == 3
    assert list(scratch.iterdir()) == []


def test_invalid_arguments_fail_when_the_step_is_added(csv_file):
    ds = Dataset.read(str(csv_file))
    with pytest.raises(ValueError):
        ds.dedup(keep="middle")
    with pytest.raises(ValueError):
        ds.rename()
    with pytest.raises(ValueError):
        ds.sample()
