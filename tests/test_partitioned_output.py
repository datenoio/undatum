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
    ).fetchall()
    assert total == [(3000, 300)]


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
    assert duckdb.sql("SELECT count(*) FROM read_parquet('pq/**/*.parquet')").fetchall() == [(4,)]


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


@pytest.mark.parametrize("hive", [True, False])
def test_null_empty_and_literal_null_markers_keep_all_records(tmp_path, monkeypatch, hive):
    from undatum.io import partition

    monkeypatch.setattr(partition, "FLUSH_ROWS", 1)
    rows = [
        {"k": None, "id": 0},
        {"k": "", "id": 1},
        {"k": HIVE_NULL, "id": 2},
        {"k": "__null__", "id": 3},
        {"k": "other", "id": 4},
        {"k": "", "id": 5},
        {"k": None, "id": 6},
    ]
    writer = PartitionedWriter(str(tmp_path / "out"), ["k"], "jsonl", hive=hive, max_open_files=1)
    assert writer.write_all(rows) == len(rows)
    assert len(writer.files) == len(set(writer.files))
    saved = [json.loads(line) for p in writer.files for line in Path(p).read_text().splitlines()]
    assert sorted(r["id"] for r in saved) == list(range(len(rows)))


@pytest.mark.parametrize("engine", ["python", "duckdb"])
def test_literal_hive_null_round_trips_separately_from_null(tmp_path, engine):
    src = tmp_path / "input.jsonl"
    src.write_text(
        "\n".join(json.dumps(r) for r in [{"k": None, "id": 1}, {"k": HIVE_NULL, "id": 2}]) + "\n"
    )
    out = tmp_path / "out"
    _invoke("convert", str(src), str(out), "--partition-by", "k", "-O", "parquet", "-e", engine)
    assert _files(out) == [
        f"k=%5F{HIVE_NULL[1:]}/data_0.parquet",
        f"k={HIVE_NULL}/data_0.parquet",
    ]
    # Verify the files independently of the reader's Hive NULL handling: DuckDB
    # 1.3/1.4 do not recognize the standard marker (their own writer uses NULL).
    for directory, record_id in ((HIVE_NULL, 1), (f"%5F{HIVE_NULL[1:]}", 2)):
        path = str(out / f"k={directory}" / "data_0.parquet").replace("'", "''")
        assert duckdb.sql(
            f"SELECT id FROM read_parquet('{path}', hive_partitioning=false)"
        ).fetchall() == [(record_id,)]
    from undatum.io.partition import _duckdb_names_null_partitions

    if not _duckdb_names_null_partitions():
        return
    escaped = str(out / "**/*.parquet").replace("'", "''")
    rows = duckdb.sql(
        f"SELECT id, k FROM read_parquet('{escaped}', hive_partitioning=true) ORDER BY id"
    ).fetchall()
    assert rows == [(1, None), (2, HIVE_NULL)]


def test_flat_composite_keys_and_numbered_parts_do_not_collide(tmp_path, monkeypatch):
    from undatum.io import partition

    monkeypatch.setattr(partition, "FLUSH_ROWS", 1)
    for fields, rows in (
        (["a", "b"], [{"a": "x_y", "b": "z", "id": 0}, {"a": "x", "b": "y_z", "id": 1}]),
        (["a"], [{"a": "x", "id": 0}, {"a": "x_1", "id": 1}, {"a": "x", "id": 2}]),
    ):
        writer = PartitionedWriter(
            str(tmp_path / f"flat_{len(fields)}"), fields, "jsonl", hive=False, max_open_files=1
        )
        writer.write_all(rows)
        assert len(writer.files) == len(set(writer.files))
        saved = [
            json.loads(line) for p in writer.files for line in Path(p).read_text().splitlines()
        ]
        assert sorted(saved, key=lambda r: r["id"]) == rows


@pytest.mark.parametrize("engine", ["python", "duckdb"])
@pytest.mark.parametrize("field", ["../outside", "/absolute", "..\\outside", "C:\\outside"])
def test_unsafe_partition_field_is_rejected_before_writing(tmp_path, engine, field):
    src = tmp_path / "input.jsonl"
    src.write_text(json.dumps({field: "x", "id": 1}) + "\n")
    out = tmp_path / "out"
    result = _invoke(
        "convert",
        str(src),
        str(out),
        "--partition-by",
        field,
        "-O",
        "parquet",
        "-e",
        engine,
        code=1,
    )
    assert isinstance(result.exception, ValidationError)
    assert not out.exists()
    assert list(tmp_path.iterdir()) == [src]


def test_partition_symlink_cannot_redirect_output(tmp_path):
    out, outside = tmp_path / "out", tmp_path / "outside"
    out.mkdir()
    outside.mkdir()
    (out / "k=x").symlink_to(outside, target_is_directory=True)
    writer = PartitionedWriter(str(out), ["k"], "jsonl")
    with pytest.raises(ValidationError, match="leaves the output directory"):
        writer.write_all([{"k": "x", "id": 1}])
    assert list(outside.iterdir()) == []


def test_flat_layout_allows_field_names_that_do_not_enter_paths(tmp_path):
    writer = PartitionedWriter(str(tmp_path / "flat"), ["path/name"], "jsonl", hive=False)
    row = {"path/name": "safe", "id": 1}
    assert writer.write_all([row]) == 1
    assert json.loads((tmp_path / "flat/safe.jsonl").read_text()) == row
