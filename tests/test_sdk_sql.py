"""Dataset methods that run the plan in DuckDB return what the Python engine returns."""

from __future__ import annotations

import datetime
import decimal
import json
import logging

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pyarrow import feather
from test_ops_contract import CASES, ROWS, _write_input

from undatum import Dataset
from undatum.common.errors import UndatumError

METHODS = {
    "head": lambda ds: ds.head(100),
    "count": lambda ds: ds.count(),
    "uniq": lambda ds: ds.uniq(["name", "city name"]),
    "frequency": lambda ds: ds.frequency("name"),
    "schema": lambda ds: ds.schema(),
}


def _typed(value):
    """A value with the types of everything in it, so 1 and 1.0 or '' and None differ."""
    if isinstance(value, dict):
        return {key: _typed(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_typed(item) for item in value]
    return (type(value).__name__, value)


def _both(path, method, steps=()):
    results = {}
    for engine in ("python", "auto"):
        ds = Dataset.read(str(path), engine=engine)
        for name, cfg in steps:
            ds = ds._then(name, cfg)
        results[engine] = _typed(method(ds))
    return results


@pytest.mark.parametrize("fmt", ["csv", "jsonl", "parquet"])
@pytest.mark.parametrize("method", list(METHODS))
@pytest.mark.parametrize("name,cfg", CASES, ids=[f"{n}-{i}" for i, (n, _) in enumerate(CASES)])
def test_methods_match_the_python_engine(tmp_path, fmt, method, name, cfg):
    results = _both(_write_input(tmp_path, fmt), METHODS[method], [(name, cfg)])
    assert results["auto"] == results["python"]


@pytest.mark.parametrize("fmt", ["csv", "jsonl", "parquet"])
@pytest.mark.parametrize("method", list(METHODS))
def test_methods_without_steps_match_the_python_engine(tmp_path, fmt, method):
    results = _both(_write_input(tmp_path, fmt), METHODS[method])
    assert results["auto"] == results["python"]


@pytest.mark.parametrize("method", ["head", "uniq", "frequency", "schema"])
def test_csv_runs_in_duckdb(tmp_path, caplog, method):
    path = _write_input(tmp_path, "csv")
    with caplog.at_level(logging.DEBUG, logger="undatum.sdk.dataset"):
        METHODS[method](Dataset.read(str(path)).rename({"id": "key"}))
    assert any("DuckDB plan" in message for message in caplog.messages)


def test_python_engine_option(tmp_path, caplog):
    path = _write_input(tmp_path, "csv")
    with caplog.at_level(logging.DEBUG, logger="undatum.sdk.dataset"):
        Dataset.read(str(path), engine="python").limit(3).frequency("name")
    assert not any("DuckDB plan" in message for message in caplog.messages)


def test_frequency_ties_keep_first_seen_order(tmp_path):
    path = tmp_path / "ties.csv"
    path.write_text("k\n" + "\n".join("cbacaad"), encoding="utf8")
    ds = Dataset.read(str(path)).rename({"k": "key"})
    assert [row["key"] for row in ds.frequency("key")] == ["a", "c", "b", "d"]
    assert [row["key"] for row in ds.uniq("key")] == ["c", "b", "a", "d"]


@pytest.mark.parametrize(
    "text",
    [
        "a,a,b\n1,2,3\n",  # repeated names
        "﻿a,b\n1,2\n",  # byte-order mark
        "a, b\n 1 , 2 \n",  # padded names
        "a,b\n1,2\n3,4,5\n",  # a long row DuckDB takes for the header
        "a,b,c\n1,2,3\n4,5\n",  # a short row
    ],
)
def test_csv_headers_duckdb_reads_otherwise_use_python(tmp_path, text):
    path = tmp_path / "messy.csv"
    path.write_text(text, encoding="utf8")
    for method in ("head", "schema"):
        results = _both(path, METHODS[method], [("rename", _rename({"zz": "yy"}))])
        assert results["auto"] == results["python"]


def _rename(mapping):
    from undatum.ops import RenameConfig

    return RenameConfig(mapping=mapping)


TYPED = {
    "int": pa.array([1, None, 3]),
    "int8": pa.array([1, None, 3], pa.int8()),
    "uint64": pa.array([1, None, 2**63], pa.uint64()),
    "float": pa.array([1.5, None, 3.0]),
    "float32": pa.array([1.5, None, 0.25], pa.float32()),
    "text": pa.array(["a", None, ""]),
    "large_text": pa.array(["a", None, ""], pa.large_string()),
    "dictionary": pa.array(["a", None, "a"]).dictionary_encode(),
    "bool": pa.array([True, None, False]),
    "date": pa.array([datetime.date(2024, 1, 2), None, datetime.date(1, 1, 1)]),
    "timestamp": pa.array([datetime.datetime(2024, 1, 2, 3, 4, 5, 6), None], pa.timestamp("us")),
    "timestamp_ms": pa.array([datetime.datetime(2024, 1, 2, 3, 4, 5), None], pa.timestamp("ms")),
    "timestamp_ns": pa.array([1, None], pa.timestamp("ns")),
    "timestamp_s": pa.array([1, None], pa.timestamp("s")),
    "time": pa.array([datetime.time(10, 30, 0, 500000), None], pa.time64("us")),
    "decimal": pa.array([decimal.Decimal("1.50"), None], pa.decimal128(10, 2)),
    "binary": pa.array([b"\x00\x01", None, b""]),
    "list": pa.array([[1, 2], None, []]),
    "struct": pa.array([{"x": 1, "y": "a"}, None, {"x": None, "y": None}]),
    "map": pa.array([[("k", 1)], None, []], pa.map_(pa.string(), pa.int64())),
    "duration": pa.array([datetime.timedelta(seconds=5), None], pa.duration("us")),
    "null": pa.array([None, None], pa.null()),
}


@pytest.mark.parametrize("fmt", ["parquet", "feather", "orc"])
@pytest.mark.parametrize("kind", list(TYPED))
def test_typed_columns_match_the_python_reader(tmp_path, fmt, kind):
    table = pa.table({"value": TYPED[kind], "n": pa.array(range(len(TYPED[kind])))})
    path = tmp_path / f"typed.{fmt}"
    if fmt == "parquet":
        pq.write_table(table, path)
    elif fmt == "feather":
        feather.write_feather(table, path)
    else:
        orc = pytest.importorskip("pyarrow.orc")
        try:
            orc.write_table(table, path)
        except (pa.ArrowNotImplementedError, pa.ArrowInvalid):
            pytest.skip(f"ORC cannot hold {kind}")
    calls = {
        "head": lambda ds: ds.limit(10).head(),
        "uniq": lambda ds: ds.uniq("value"),
        "frequency": lambda ds: ds.frequency("value"),
    }
    for method, call in calls.items():
        if method != "head" and kind in ("list", "struct", "map", "null"):
            continue  # Python compares nested values by repr()
        try:
            expected = _typed(call(Dataset.read(str(path), engine="python")))
        except Exception as exc:  # noqa: BLE001 - the Python reader cannot read every type
            pytest.skip(f"the Python reader fails on {kind}: {exc}")
        assert _typed(call(Dataset.read(str(path)))) == expected, method


def test_json_values_stay_with_python(tmp_path, caplog):
    path = tmp_path / "x.jsonl"
    rows = [{"day": "2024-01-02", "n": 1}, {"day": "2024-01-03", "n": 1.5}, {"n": 2}]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf8")
    ds = Dataset.read(str(path)).limit(5)
    assert ds.head() == rows
    assert [row["day"] for row in ds.frequency("day")] == ["2024-01-02", "2024-01-03", None]
    assert [row["n"] for row in ds.uniq("n")] == [1, 1.5, 2]
    with caplog.at_level(logging.DEBUG, logger="undatum.sdk.dataset"):
        assert ds.count() == 3
    assert any("DuckDB plan" in message for message in caplog.messages)


class TestArrow:
    def test_csv_to_arrow_keeps_text(self, tmp_path, caplog):
        path = _write_input(tmp_path, "csv")
        with caplog.at_level(logging.DEBUG, logger="undatum.sdk.dataset"):
            table = Dataset.read(str(path)).select(["id", "name"]).to_arrow()
        assert any("DuckDB plan" in message for message in caplog.messages)
        assert table.column_names == ["id", "name"]
        assert table.to_pylist() == [{"id": r["id"], "name": r["name"]} for r in ROWS]
        python = Dataset.read(str(path), engine="python").select(["id", "name"]).to_arrow()
        assert python.to_pylist() == table.to_pylist()

    def test_parquet_to_arrow(self, tmp_path):
        path = _write_input(tmp_path, "parquet")
        table = Dataset.read(str(path)).to_arrow()
        assert isinstance(table, pa.Table)
        assert table.num_rows == len(ROWS)

    @pytest.mark.parametrize("engine", ["auto", "python"])
    def test_chunks_have_the_requested_size(self, tmp_path, engine):
        path = _write_input(tmp_path, "csv")
        chunks = list(Dataset.read(str(path), engine=engine).to_arrow(chunksize=4))
        assert [chunk.num_rows for chunk in chunks] == [4, 2]
        frames = list(Dataset.read(str(path), engine=engine).to_pandas(chunksize=5))
        assert [len(frame) for frame in frames] == [5, 1]

    def test_records_with_other_fields_later(self):
        records = [{"a": 1}] * 3 + [{"a": 2.5, "b": "x"}]
        ds = Dataset.from_records(records)
        table = ds.to_arrow()
        assert table.column_names == ["a", "b"]
        assert table.column("a").to_pylist() == [1.0, 1.0, 1.0, 2.5]
        assert table.column("b").to_pylist() == [None, None, None, "x"]

    def test_mixed_types(self):
        ds = Dataset.from_records([{"a": 1}, {"a": "x"}])
        with pytest.raises(UndatumError, match="'a'"):
            ds.to_arrow()
        assert ds.to_pandas()["a"].tolist() == [1, "x"]

    def test_types_changing_between_chunks(self, monkeypatch):
        import undatum.sdk.dataset as module

        monkeypatch.setattr(module, "BATCH_ROWS", 2)
        ds = Dataset.from_records([{"a": 1}, {"a": 2}, {"a": "x"}])
        with pytest.raises(UndatumError):
            ds.to_arrow()
        assert ds.to_pandas()["a"].tolist() == [1, 2, "x"]

    def test_empty(self, tmp_path):
        assert Dataset.from_records([]).to_arrow().num_rows == 0
        assert Dataset.from_records([]).to_pandas().empty

    def test_polars(self, tmp_path):
        pl = pytest.importorskip("polars")
        path = _write_input(tmp_path, "parquet")
        frame = Dataset.read(str(path)).select(["id", "name"]).to_polars()
        assert isinstance(frame, pl.DataFrame)
        assert frame.columns == ["id", "name"]
        assert frame.height == len(ROWS)
        chunks = list(Dataset.from_records(ROWS).to_polars(chunksize=4))
        assert [chunk.height for chunk in chunks] == [4, 2]
