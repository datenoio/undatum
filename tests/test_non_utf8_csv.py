"""The DuckDB engine never drops CSV rows silently (non-UTF-8 text, unreadable rows)."""

from __future__ import annotations

import csv
import gzip
import json
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from undatum.common.command_utils import duckdb_can_decode, duckdb_read_csv_options
from undatum.common.engine_selector import detect_engine
from undatum.common.errors import UndatumError
from undatum.core import app
from undatum.io import open_source
from undatum.ops.runner import BATCH_ROWS, write_query

duckdb = pytest.importorskip("duckdb")

runner = CliRunner()

ROWS = [[f"00{7700000000 + i}", f"Компания {i}", str(i)] for i in range(50)]


def _write_csv(path, encoding):
    lines = ["inn;name;amount"] + [";".join(row) for row in ROWS]
    path.write_bytes(("\n".join(lines) + "\n").encode(encoding))
    return path


@pytest.fixture
def cp1251_csv(tmp_path):
    return _write_csv(tmp_path / "companies.csv", "cp1251")


@pytest.fixture
def utf8_csv(tmp_path):
    return _write_csv(tmp_path / "companies_utf8.csv", "utf-8")


def _read_rows(path):
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


class TestDuckdbCanDecode:
    def test_utf8(self, utf8_csv):
        assert duckdb_can_decode(str(utf8_csv))

    def test_cp1251(self, cp1251_csv):
        assert not duckdb_can_decode(str(cp1251_csv))

    def test_gzip(self, tmp_path, cp1251_csv, utf8_csv):
        bad = tmp_path / "bad.csv.gz"
        bad.write_bytes(gzip.compress(cp1251_csv.read_bytes()))
        good = tmp_path / "good.csv.gz"
        good.write_bytes(gzip.compress(utf8_csv.read_bytes()))
        assert not duckdb_can_decode(str(bad), "gz")
        assert duckdb_can_decode(str(good), "gz")

    @pytest.mark.parametrize(
        ("encoding", "expected"),
        [("UTF-8", True), ("utf8", True), ("ascii", True), ("cp1251", False), ("nope", False)],
    )
    def test_explicit_encoding(self, utf8_csv, encoding, expected):
        assert duckdb_can_decode(str(utf8_csv), encoding=encoding) is expected

    def test_character_cut_at_the_end_of_the_sample(self, tmp_path):
        path = tmp_path / "long.csv"
        path.write_bytes(b"a" * ((1 << 20) - 1) + "Ж\n".encode())
        assert duckdb_can_decode(str(path))

    def test_missing_file_is_left_to_the_reader(self, tmp_path):
        assert duckdb_can_decode(str(tmp_path / "missing.csv"))


def test_duckdb_reports_unreadable_rows_by_default():
    assert "ignore_errors" not in duckdb_read_csv_options(",")
    assert "ignore_errors=true" in duckdb_read_csv_options(",", ignore_errors=True)


def test_auto_engine_reads_non_utf8_csv_with_python(cp1251_csv, utf8_csv):
    assert detect_engine(str(cp1251_csv), "auto", "csv") == "iterable"
    assert detect_engine(str(cp1251_csv), "duckdb", "csv") == "duckdb"
    assert detect_engine(str(utf8_csv), "auto", "csv") == "duckdb"
    assert open_source(str(cp1251_csv)).duckdb_from() is None
    assert open_source(str(utf8_csv)).duckdb_from() is not None


@pytest.mark.parametrize(
    "args",
    [
        ["head", "-n", "3"],
        ["sort", "--by", "amount"],
        ["select", "--fields", "inn,name", "--where", "amount > 10"],
    ],
)
def test_record_commands_keep_every_cp1251_row(tmp_path, cp1251_csv, args):
    out = tmp_path / "out.csv"
    result = runner.invoke(app, [args[0], str(cp1251_csv), *args[1:], "-o", str(out)])
    assert result.exit_code == 0, result.output
    rows = _read_rows(out)
    expected = {"head": 3, "sort": 50, "select": 39}[args[0]]
    assert len(rows) == expected + 1
    assert rows[1][1].startswith("Компания")


def test_stats_counts_every_cp1251_row(tmp_path, cp1251_csv):
    out = tmp_path / "stats.json"
    result = runner.invoke(app, ["stats", str(cp1251_csv), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text(encoding="utf-8"))["count"] == len(ROWS)


class _FailingResult:
    """DuckDB result whose second fetch fails, like a bad byte late in a CSV file."""

    description = [("v", "INTEGER")]

    def __init__(self, good_fetches):
        self.good_fetches = good_fetches

    def fetchmany(self, size):
        if self.good_fetches == 0:
            raise duckdb.InvalidInputException("Invalid unicode (byte sequence mismatch)")
        self.good_fetches -= 1
        return [(i,) for i in range(size)]


class _Connection:
    def __init__(self, good_fetches):
        self.result = _FailingResult(good_fetches)

    def sql(self, query):
        assert query.startswith("DESCRIBE")
        return SimpleNamespace(fetchall=lambda: [("v", "INTEGER")])

    def execute(self, query):
        return self.result


def test_failure_after_records_reached_stdout_is_an_error(capfd):
    with pytest.raises(UndatumError, match="--engine python"):
        write_query(_Connection(good_fetches=1), "SELECT v", None)
    # The first batch was printed once; it must not be printed again by a fallback.
    assert capfd.readouterr().out.count("\n") == BATCH_ROWS


def test_failure_before_any_record_lets_the_caller_fall_back(capfd):
    with pytest.raises(duckdb.Error):
        write_query(_Connection(good_fetches=0), "SELECT v", None)
    assert capfd.readouterr().out == ""


@pytest.mark.parametrize("engine", ["python", "auto"])
def test_convert_detects_the_encoding(tmp_path, cp1251_csv, engine):
    # --encoding is optional, as in the other commands (it was utf8 by default).
    out = tmp_path / "out.jsonl"
    result = runner.invoke(app, ["convert", "-e", engine, str(cp1251_csv), str(out)])
    assert result.exit_code == 0, result.output
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(ROWS)
    assert rows[0] == {"inn": ROWS[0][0], "name": "Компания 0", "amount": "0"}


def test_convert_honours_an_explicit_encoding(tmp_path, cp1251_csv):
    out = tmp_path / "out.jsonl"
    args = ["convert", "-e", "python", "--encoding", "latin-1", str(cp1251_csv), str(out)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    first = json.loads(out.read_text(encoding="utf-8").splitlines()[0])
    assert first["name"] == "Компания 0".encode("cp1251").decode("latin-1")


def test_flatten_split_and_validate_detect_the_encoding(tmp_path, cp1251_csv, monkeypatch):
    result = runner.invoke(app, ["flatten", str(cp1251_csv)])
    assert result.exit_code == 0, result.output
    assert "Компания 0" in result.output

    parts = tmp_path / "parts"
    parts.mkdir()
    monkeypatch.chdir(parts)  # split -f writes <value>.csv here
    result = runner.invoke(app, ["split", str(cp1251_csv), "-f", "amount"])
    assert result.exit_code == 0, result.output
    assert len(list(parts.glob("*.csv"))) == len(ROWS)
    assert "Компания 7" in (parts / "7.csv").read_text(encoding="utf-8")

    out = tmp_path / "valid.csv"
    args = ["validate", str(cp1251_csv), "-f", "name", "--rule", "common.email", "-o", str(out)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "Компания 0" in out.read_text(encoding="utf-8")
