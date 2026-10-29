"""Inputs DuckDB reads through Arrow (ORC, Arrow/Feather) give the Python engine's results."""

from __future__ import annotations

import csv
import datetime
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pyarrow import feather
from typer.testing import CliRunner

from undatum.core import app
from undatum.io import RowSource

runner = CliRunner()

ROWS = [
    {
        "n": i,
        "x": i / 4,
        "flag": i % 2 == 0,
        "city": ["Berlin", "Paris", "Рим", None][i % 4],
        "day": datetime.date(2024, 1, 1 + i % 28),
        "note": f'say "hi", {i}',
    }
    for i in range(40)
]


def _write(directory, fmt):
    table = pa.Table.from_pylist(ROWS)
    if fmt == "orc":
        orc = pytest.importorskip("pyarrow.orc")
        path = directory / "in.orc"
        orc.write_table(table, path, stripe_size=1024)  # several stripes
    else:
        path = directory / "in.feather"
        feather.write_feather(table, path, chunksize=7)  # several record batches
    return path


def _read(path):
    if path.suffix == ".parquet":
        return pq.read_table(path).to_pylist()
    if path.suffix == ".csv":
        with open(path, newline="", encoding="utf8") as handle:
            return list(csv.DictReader(handle))
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]


def _run(args, engine):
    result = runner.invoke(app, [*args, "--engine", engine])
    assert result.exit_code == 0, result.output
    return result.stdout


@pytest.fixture(params=["orc", "feather"])
def source(request, tmp_path):
    return _write(tmp_path, request.param)


def test_reader_and_relation(source):
    import duckdb

    assert RowSource(str(source), {}).arrow_reader().read_all().num_rows == len(ROWS)
    conn = duckdb.connect()
    relation = RowSource(str(source), {}).duckdb_relation(conn, ["city"])
    assert conn.execute(f"SELECT count(*) FROM {relation}").fetchall() == [(len(ROWS),)]
    assert [row[0] for row in conn.execute(f"DESCRIBE {relation}").fetchall()] == ["city"]


@pytest.mark.parametrize(
    "args",
    [
        ["frequency", "{src}", "-f", "city"],
        ["frequency", "{src}", "-f", "city,flag"],
        ["uniq", "{src}", "-f", "city"],
        ["uniq", "{src}", "-f", "city", "-O", "jsonl"],
    ],
)
def test_aggregates_match_the_python_engine(source, args):
    args = [str(source) if a == "{src}" else a for a in args]
    assert sorted(_run(args, "auto").splitlines()) == sorted(_run(args, "python").splitlines())


@pytest.mark.parametrize("output", ["jsonl", "csv", "parquet"])
@pytest.mark.parametrize(
    "command",
    [
        ["sort", "{src}", "--by", "x", "--desc"],
        ["rename", "{src}", "--map", "city:town"],
        ["head", "{src}", "-n", "5"],
        ["dedup", "{src}", "--key-fields", "city"],
    ],
)
def test_row_commands_match_the_python_engine(source, tmp_path, command, output):
    results = {}
    for engine in ("python", "auto"):
        target = tmp_path / f"{engine}.{output}"
        args = [str(source) if a == "{src}" else a for a in command]
        _run([*args, "-o", str(target)], engine)
        results[engine] = _read(target)
    assert results["auto"] == results["python"]


@pytest.mark.parametrize("output", ["jsonl", "csv", "parquet"])
def test_convert_matches_the_python_engine(source, tmp_path, output):
    results = {}
    for engine in ("python", "auto"):
        target = tmp_path / f"{engine}.{output}"
        _run(["convert", str(source), str(target)], engine)
        results[engine] = _read(target)
    assert results["auto"] == results["python"]


def test_duckdb_reads_the_arrow_input(source, caplog):
    with caplog.at_level("DEBUG", logger="undatum.common.engine_selector"):
        _run(["frequency", str(source), "-f", "city"], "auto")
    assert any("read through Arrow" in message for message in caplog.messages)


def test_formats_without_an_arrow_reader_use_python(tmp_path):
    from undatum.common.writer import write_records

    path = tmp_path / "in.avro"
    write_records(str(path), [{"n": row["n"], "city": row["city"]} for row in ROWS[:3]])
    assert RowSource(str(path), {}).arrow_reader() is None
    assert not RowSource(str(path), {}).duckdb_readable()


def test_feather_v1_uses_python(tmp_path):
    path = tmp_path / "v1.feather"
    feather.write_feather(pa.Table.from_pylist(ROWS[:3]), path, version=1)
    assert RowSource(str(path), {}).arrow_reader() is None
