"""Hive-partitioned output: ``convert --partition-by`` and ``split --fields [--hive]``."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from undatum.common.errors import ValidationError
from undatum.core import app
from undatum.io.partition import HIVE_NULL, PartitionedWriter, flat_value, hive_value

CSV = "id,year,month,region,v\n1,2024,1,north,a\n2,2024,2,south,b\n3,2025,1,a/b c,c\n4,2025,1,,d\n"


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "s.csv").write_text(CSV, encoding="utf8")
    return tmp_path


def _invoke(*args, code=0):
    result = CliRunner().invoke(app, list(args))
    assert result.exit_code == code, result.output
    return result


def _files(directory: Path) -> list[str]:
    return sorted(str(p.relative_to(directory)) for p in directory.rglob("*") if p.is_file())


@pytest.mark.parametrize("engine", ["duckdb", "python"])
def test_convert_hive_parquet_round_trip(data, engine):
    _invoke(
        "convert", "s.csv", "out", "--partition-by", "year,month", "-O", "parquet", "-e", engine
    )
    assert _files(data / "out") == [
        "year=2024/month=1/data_0.parquet",
        "year=2024/month=2/data_0.parquet",
        "year=2025/month=1/data_0.parquet",
    ]
    rows = duckdb.sql(
        "SELECT id, year, month, v FROM read_parquet('out/**/*.parquet', hive_partitioning=true) "
        "ORDER BY id"
    ).fetchall()
    assert rows == [
        ("1", 2024, 1, "a"),
        ("2", 2024, 2, "b"),
        ("3", 2025, 1, "c"),
        ("4", 2025, 1, "d"),
    ]
    # The partition fields live in the directory names, not in the files.
    columns = duckdb.sql(
        "DESCRIBE SELECT * FROM read_parquet('out/year=2024/month=1/data_0.parquet', "
        "hive_partitioning=false)"
    ).fetchall()
    assert [c[0] for c in columns] == ["id", "region", "v"]


def test_engines_write_the_same_layout(data):
    for engine in ("duckdb", "python"):
        _invoke(
            "convert", "s.csv", f"o_{engine}", "--partition-by", "region", "-O", "csv", "-e", engine
        )
    assert (
        _files(data / "o_duckdb")
        == _files(data / "o_python")
        == [
            f"region={HIVE_NULL}/data_0.csv",
            "region=a%2Fb%20c/data_0.csv",
            "region=north/data_0.csv",
            "region=south/data_0.csv",
        ]
    )
    read = "SELECT * FROM read_csv('{}/**/*.csv', hive_partitioning=true) ORDER BY id"
    assert (
        duckdb.sql(read.format("o_duckdb")).fetchall()
        == duckdb.sql(read.format("o_python")).fetchall()
    )


def test_duckdb_before_1_5_falls_back_to_python(data, monkeypatch):
    # DuckDB 1.3 and 1.4 name the NULL partition "region=NULL", not HIVE_NULL.
    monkeypatch.setattr(duckdb, "__version__", "1.4.4")
    _invoke("convert", "s.csv", "o", "--partition-by", "region", "-O", "csv", "-e", "duckdb")
    assert f"region={HIVE_NULL}/data_0.csv" in _files(data / "o")


def test_jsonl_and_where(data):
    _invoke(
        "convert", "s.csv", "j", "--partition-by", "year", "-O", "jsonl", "--where", "month = 1"
    )
    assert _files(data / "j") == ["year=2024/data_0.jsonl", "year=2025/data_0.jsonl"]
    lines = (data / "j/year=2025/data_0.jsonl").read_text().splitlines()
    assert [json.loads(line)["id"] for line in lines] == ["3", "4"]


def test_output_directory_must_be_empty(data):
    (data / "busy").mkdir()
    (data / "busy" / "x.txt").write_text("keep me")
    result = _invoke("convert", "s.csv", "busy", "--partition-by", "year", "-O", "csv", code=1)
    assert "not empty" in str(result.exception)
    assert (data / "busy" / "x.txt").read_text() == "keep me"


@pytest.mark.parametrize("engine", ["duckdb", "python"])
def test_unknown_partition_field(data, engine):
    result = _invoke(
        "convert", "s.csv", "o", "--partition-by", "regoin", "-O", "csv", "-e", engine, code=1
    )
    assert isinstance(result.exception, ValidationError)
    assert "regoin" in str(result.exception)


@pytest.mark.parametrize("engine", ["duckdb", "python"])
def test_high_cardinality_keys(tmp_path, monkeypatch, engine):
    monkeypatch.chdir(tmp_path)
    with open("many.csv", "w", newline="", encoding="utf8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "key"])
        for i in range(3000):
            writer.writerow([i, i % 300])  # 300 keys, interleaved
    _invoke(
        "convert",
        "many.csv",
        "out",
        "--partition-by",
        "key",
        "-O",
        "csv",
        "--max-open-files",
        "8",
        "-e",
        engine,
    )
    assert len(os.listdir("out")) == 300
    total = duckdb.sql(
        "SELECT count(*), count(DISTINCT key) FROM read_csv('out/**/*.csv', hive_partitioning=true)"
    ).fetchone()
    assert total == (3000, 300)


def test_writer_bounds_open_files(tmp_path):
    writer = PartitionedWriter(str(tmp_path / "w"), ["k"], "jsonl", max_open_files=2)
    rows = [{"k": i % 5, "n": i} for i in range(50)]
    assert writer.write_all(rows) == 50
    written = [json.loads(line) for f in writer.files for line in Path(f).read_text().splitlines()]
    assert sorted(r["n"] for r in written) == list(range(50))


def test_split_hive_flat_and_chunks(data):
    _invoke("split", "s.csv", "--fields", "region", "--hive", "--dirname", "parts")
    assert "region=north/data_0.csv" in _files(data / "parts")
    _invoke("split", "s.csv", "--fields", "region", "--dirname", "flat")
    assert _files(data / "flat") == ["__null__.csv", "a%2Fb c.csv", "north.csv", "south.csv"]
    # The flat layout keeps the field inside the files.
    assert (data / "flat/north.csv").read_text().splitlines()[0] == "id,year,month,region,v"
    _invoke("split", "s.csv", "--chunksize", "3", "--dirname", "chunks")
    assert _files(data / "chunks") == ["s_1.csv", "s_2.csv"]
    _invoke("split", "s.csv", "--fields", "year", "--hive", "--dirname", "pq", "-O", "parquet")
    assert duckdb.sql("SELECT count(*) FROM read_parquet('pq/**/*.parquet')").fetchone() == (4,)


def test_split_hive_needs_fields(data):
    _invoke("split", "s.csv", "--hive", "--dirname", "x", code=1)


def test_key_encoding():
    assert hive_value(None) == hive_value("") == HIVE_NULL
    assert hive_value("a/b c") == "a%2Fb%20c"
    assert hive_value("x=y") == "x%3Dy"
    assert hive_value("Ünï") == "%C3%9Cn%C3%AF"
    assert hive_value(2024) == "2024"
    assert flat_value(None) == flat_value("") == "__null__"
    assert flat_value("a/b c") == "a%2Fb c"
