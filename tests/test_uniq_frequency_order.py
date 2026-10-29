"""uniq and frequency give values in first-seen order (ties too) with either engine."""

from __future__ import annotations

import csv
import io
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from undatum.core import app

runner = CliRunner()

# a: 3, c: 2, b: 1, d: 1
VALUES = list("cbacaad")


def _write(tmp_path, fmt, values):
    path = tmp_path / f"data.{fmt}"
    rows = [{"k": value, "n": str(i)} for i, value in enumerate(values)]
    if fmt == "csv":
        path.write_text("k,n\n" + "".join(f"{r['k']},{r['n']}\n" for r in rows), encoding="utf8")
    elif fmt == "jsonl":
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf8")
    else:
        pq.write_table(pa.Table.from_pylist(rows), path)
    return str(path)


@pytest.fixture
def no_fallback(monkeypatch):
    """Fail when a DuckDB command falls back to the Python reader."""
    from undatum.cmds import selector

    def python_reader(*args, **kwargs):
        raise AssertionError("fell back to the Python engine")

    monkeypatch.setattr(selector, "open_iterable", python_reader)


def _rows(*args):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return list(csv.reader(io.StringIO(result.output)))[1:]


@pytest.mark.parametrize("engine", ["python", "duckdb"])
@pytest.mark.parametrize("fmt", ["csv", "jsonl", "parquet"])
def test_ties_in_first_seen_order(tmp_path, request, fmt, engine):
    if engine == "duckdb":
        request.getfixturevalue("no_fallback")
    path = _write(tmp_path, fmt, VALUES)
    assert _rows("frequency", "-e", engine, "-f", "k", path) == [
        ["a", "3"],
        ["c", "2"],
        ["b", "1"],
        ["d", "1"],
    ]
    assert _rows("uniq", "-e", engine, "-f", "k", path) == [["c"], ["b"], ["a"], ["d"]]


@pytest.mark.parametrize("engine", ["python", "duckdb"])
def test_order_after_a_filter(tmp_path, request, engine):
    if engine == "duckdb":
        request.getfixturevalue("no_fallback")
    path = _write(tmp_path, "csv", VALUES)
    args = ["-e", engine, "-f", "k", "--filter", "`k` != 'c'", path]
    assert _rows("uniq", *args) == [["b"], ["a"], ["d"]]
    assert _rows("frequency", *args) == [["a", "3"], ["b", "1"], ["d", "1"]]


def test_first_seen_order_with_threads(tmp_path, no_fallback):
    # Every value appears six times, first at scattered positions of a 300k-row file.
    values = [f"v{(i * 7919) % 50_000}" for i in range(300_000)]
    path = _write(tmp_path, "csv", values)
    expected = list(dict.fromkeys(values))
    options = ["-e", "duckdb", "--duckdb-threads", "4", "-f", "k", path]
    assert [row[0] for row in _rows("uniq", *options)] == expected
    assert [row[0] for row in _rows("frequency", *options)] == expected
