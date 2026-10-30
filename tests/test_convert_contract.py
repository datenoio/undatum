"""convert gives the same records whether DuckDB or the Python engine writes the output."""

from __future__ import annotations

import csv
import datetime
import gzip
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from undatum.core import app

runner = CliRunner()

TEXT_ROWS = [
    {"id": "1", "name": "Alice", "note": 'say "hi"', "city name": "Berlin", "code": "007"},
    {"id": "2", "name": "", "note": "a,b", "city name": "Paris", "code": ""},
    {"id": "3", "name": "Écrit", "note": "line\nbreak", "city name": "", "code": "1.50"},
    {"id": "4", "name": "Компания", "note": "tab\there", "city name": "Rome", "code": "x"},
]

TYPED_ROWS = [
    {"n": 1, "x": 1.5, "flag": True, "s": "a", "ts": datetime.datetime(2020, 1, 2, 3, 4, 5)},
    {"n": 2, "x": None, "flag": False, "s": None, "ts": None},
]

NUMERIC_ROWS = [
    {
        "n": 1,
        "big": 9007199254740993,
        "x": 0.1 + 0.2,
        "flag": True,
        "s": "a",
        "day": datetime.date(2024, 2, 29),
    },
    {"n": -2, "big": None, "x": 1e-7, "flag": False, "s": None, "day": None},
]

OUTPUTS = ["csv", "tsv", "jsonl", "json", "parquet", "csv.gz", "jsonl.zst"]


def _write_input(directory, kind):
    if kind == "csv":
        path = directory / "in.csv"
        with open(path, "w", newline="", encoding="utf8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(TEXT_ROWS[0]))
            writer.writeheader()
            writer.writerows(TEXT_ROWS)
    elif kind == "jsonl":
        path = directory / "in.jsonl"
        lines = [json.dumps(row, ensure_ascii=False) for row in TEXT_ROWS]
        path.write_text("\n".join(lines) + "\n", encoding="utf8")
    elif kind == "parquet":
        path = directory / "in.parquet"
        pq.write_table(pa.Table.from_pylist(TEXT_ROWS), path)
    elif kind == "numeric":
        path = directory / "numeric.parquet"
        pq.write_table(pa.Table.from_pylist(NUMERIC_ROWS), path)
    else:  # typed parquet: numbers, booleans, timestamps and nulls
        path = directory / "typed.parquet"
        pq.write_table(pa.Table.from_pylist(TYPED_ROWS), path)
    return path


def _read_output(path):
    name = path.name
    opener = gzip.open if name.endswith(".gz") else open
    if name.endswith(".zst"):
        import zstandard

        text = zstandard.ZstdDecompressor().decompress(path.read_bytes(), 1 << 24).decode()
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    if name.endswith(".parquet"):
        return pq.read_table(path).to_pylist()
    if ".csv" in name or name.endswith(".tsv"):
        with opener(path, "rt", newline="", encoding="utf8") as handle:
            delimiter = "\t" if name.endswith(".tsv") else ","
            return list(csv.DictReader(handle, delimiter=delimiter))
    if name.endswith(".json"):
        return json.loads(path.read_text(encoding="utf8"))
    with opener(path, "rt", encoding="utf8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _convert(source, target, engine):
    result = runner.invoke(app, ["convert", str(source), str(target), "--engine", engine])
    assert result.exit_code == 0, result.output
    return _read_output(target)


@pytest.mark.parametrize("output", OUTPUTS)
@pytest.mark.parametrize("kind", ["csv", "jsonl", "parquet", "numeric", "typed"])
def test_engines_write_the_same_records(tmp_path, kind, output):
    source = _write_input(tmp_path, kind)
    expected = _convert(source, tmp_path / f"python.{output}", "python")
    assert _convert(source, tmp_path / f"auto.{output}", "auto") == expected


@pytest.mark.parametrize("output", ["jsonl", "csv", "parquet"])
def test_text_inputs_are_written_by_duckdb(tmp_path, caplog, output):
    source = _write_input(tmp_path, "csv")
    with caplog.at_level("INFO", logger="undatum.cmds.converter"):
        _convert(source, tmp_path / f"out.{output}", "auto")
    assert any("written by DuckDB" in message for message in caplog.messages)


def test_values_duckdb_writes_differently_use_the_python_writer(tmp_path, caplog):
    source = _write_input(tmp_path, "typed")
    with caplog.at_level("DEBUG", logger="undatum.cmds.converter"):
        _convert(source, tmp_path / "out.csv", "auto")
    assert not any("written by DuckDB" in message for message in caplog.messages)


def test_empty_csv_fields_stay_empty_strings_in_json(tmp_path):
    source = _write_input(tmp_path, "csv")
    records = _convert(source, tmp_path / "out.jsonl", "auto")
    assert records[1]["name"] == ""
    assert records[1]["code"] == ""


@pytest.mark.parametrize("engine", ["auto", "python"])
def test_times_survive_conversion_to_json_lines(tmp_path, engine):
    # iterabledata JSON writers wrote null for TIME values before 1.1; DuckDB keeps them. DuckDB
    # writes the file: pyarrow 16 (the lowest-dependency CI job) writes a TIME column that
    # DuckDB reads as TIME WITH TIME ZONE.
    import duckdb

    source = tmp_path / "times.parquet"
    duckdb.sql(f"COPY (SELECT TIME '10:00:00.123456' AS at) TO '{source}' (FORMAT parquet)")
    assert _convert(source, tmp_path / "out.jsonl", engine) == [{"at": "10:00:00.123456"}]
