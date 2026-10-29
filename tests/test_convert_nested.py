"""Nested records converted to flat formats keep every record, and write errors fail."""

from __future__ import annotations

import csv
import gzip
import json

import pytest
from typer.testing import CliRunner

from undatum.cmds.converter import Converter
from undatum.common.errors import ConversionError
from undatum.core import app

runner = CliRunner()

RECORDS = [
    {
        "id": i,
        "name": name,
        "address": {"city": city, "country": "DE"},
        "items": [{"sku": f"S{i}", "qty": 1}],
        "tags": ["a", "b"],
    }
    for i, (name, city) in enumerate([("Alice", "Berlin"), ("Bob", "Paris"), ("Eve", "Rome")])
]


@pytest.fixture
def nested(tmp_path):
    path = tmp_path / "nested.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in RECORDS), encoding="utf8")
    return path


def _rows(path, delimiter=","):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def _expected():
    """Nested values as text, as the other commands write them (``head --output``)."""
    return [{key: str(value) for key, value in record.items()} for record in RECORDS]


@pytest.mark.parametrize(
    "args",
    [[], ["--flatten-data"], ["--no-flatten-data"], ["--engine", "python"], ["--threads", "2"]],
    ids=["default", "flatten-data", "no-flatten-data", "python", "threads"],
)
def test_nested_jsonl_to_csv_keeps_records(nested, tmp_path, args):
    out = tmp_path / "out.csv"
    result = runner.invoke(app, ["convert", str(nested), str(out), *args])
    assert result.exit_code == 0, result.output
    assert _rows(out) == _expected()


def test_same_text_as_other_commands(nested, tmp_path):
    converted, written = tmp_path / "converted.csv", tmp_path / "head.csv"
    assert runner.invoke(app, ["convert", str(nested), str(converted)]).exit_code == 0
    assert runner.invoke(app, ["head", str(nested), "--output", str(written)]).exit_code == 0
    assert _rows(converted) == _rows(written)


@pytest.mark.parametrize("name,delimiter", [("out.tsv", "\t"), ("out.csv.gz", ",")])
def test_other_flat_outputs(nested, tmp_path, name, delimiter):
    out = tmp_path / name
    Converter().convert(str(nested), str(out), {"progress": False})
    assert _rows(out, delimiter) == _expected()


def test_nested_outputs_keep_structures(nested, tmp_path):
    pq = pytest.importorskip("pyarrow.parquet")
    out = tmp_path / "out.parquet"
    Converter().convert(str(nested), str(out), {"progress": False})
    assert pq.read_table(out).to_pylist()[0]["address"] == {"city": "Berlin", "country": "DE"}


def test_flatten_data_writes_text_in_any_format(nested, tmp_path):
    out = tmp_path / "out.jsonl"
    Converter().convert(str(nested), str(out), {"progress": False, "flatten": True})
    first = json.loads(out.read_text(encoding="utf8").splitlines()[0])
    assert first["address"] == str(RECORDS[0]["address"])


def _failing_convert(*args, **kwargs):
    from iterable.types import ConversionResult

    return ConversionResult(
        rows_in=3, rows_out=1, elapsed_seconds=0.0, errors=[ValueError("bad record")]
    )


def test_write_errors_fail(nested, tmp_path, monkeypatch):
    import iterable.convert

    monkeypatch.setattr(iterable.convert, "convert", _failing_convert)
    out = tmp_path / "out.csv"
    with pytest.raises(ConversionError, match="2 of 3 records were not written; bad record"):
        Converter().convert(str(nested), str(out), {"progress": False, "engine": "python"})
    result = runner.invoke(app, ["convert", str(nested), str(out), "--engine", "python"])
    assert result.exit_code == 1
    assert isinstance(result.exception, ConversionError)


def test_bulk_write_errors_fail(nested, tmp_path, monkeypatch):
    from iterable.convert import core

    monkeypatch.setattr(core, "convert", _failing_convert)
    with pytest.raises(ConversionError, match="bad record"):
        Converter().bulk_convert(
            str(tmp_path / "*.jsonl"), str(tmp_path / "out"), {"progress": False}, to_ext="csv"
        )
