"""Empty CSV fields are empty strings on DuckDB, as in the Python reader's records."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from undatum.cmds.statistics import StatProcessor
from undatum.core import app

runner = CliRunner()

# Empty fields, unquoted and quoted ("").
LEFT = 'k,v\nb,1\n,2\na,3\n"",4\n'
RIGHT = "k,w\n,x\na,y\n"


@pytest.fixture
def files(tmp_path):
    left = tmp_path / "left.csv"
    right = tmp_path / "right.csv"
    left.write_text(LEFT, encoding="utf8")
    right.write_text(RIGHT, encoding="utf8")
    return str(left), str(right)


def _run(*args):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


@pytest.mark.parametrize(
    "command",
    [
        ["head", "{left}", "-O", "jsonl"],
        ["head", "{left}"],
        ["select", "-f", "k", "{left}", "-O", "jsonl"],
        ["sort", "--by", "k", "{left}", "-O", "jsonl"],
        ["dedup", "--key-fields", "k", "{left}", "-O", "jsonl"],
        ["uniq", "-f", "k", "{left}", "-O", "jsonl"],
        ["frequency", "-f", "k", "{left}", "-O", "jsonl"],
        ["join", "{left}", "{right}", "--on", "k", "-O", "jsonl"],
    ],
    ids=lambda command: "-".join(part for part in command if not part.startswith(("{", "-"))),
)
def test_engines_agree(files, command):
    left, right = files
    args = [arg.replace("{left}", left).replace("{right}", right) for arg in command]
    outputs = {engine: _run(args[0], "-e", engine, *args[1:]) for engine in ("python", "duckdb")}
    assert outputs["duckdb"] == outputs["python"]
    assert "null" not in outputs["duckdb"]


def test_join_keeps_rows_with_empty_keys(files):
    left, right = files
    rows = [
        json.loads(line)
        for line in _run("join", left, right, "--on", "k", "-O", "jsonl").splitlines()
    ]
    assert sorted((row["k"], row["v"]) for row in rows) == [("", "2"), ("", "4"), ("a", "3")]


@pytest.mark.parametrize("command", [["head"], ["convert"]])
def test_csv_files_write_empty_fields_unquoted(files, tmp_path, command):
    left, _ = files
    texts = {}
    for engine in ("python", "duckdb"):
        out = tmp_path / f"{engine}.csv"
        if command[0] == "head":
            _run("head", "-e", engine, left, "-o", str(out))
        else:
            _run("convert", "-e", engine, left, str(out))
        texts[engine] = out.read_bytes()
    assert texts["duckdb"] == texts["python"]
    assert texts["duckdb"] == b"k,v\r\nb,1\r\n,2\r\na,3\r\n,4\r\n"


def test_partitioned_csv_writes_empty_fields_unquoted(files, tmp_path):
    left, _ = files
    out = tmp_path / "parts"
    _run("convert", "-e", "duckdb", left, str(out), "--partition-by", "v", "-O", "csv")
    texts = sorted(path.read_text(encoding="utf8") for path in out.rglob("*.csv"))
    assert all('""' not in text for text in texts)
    assert any(text.splitlines()[1:] == [""] for text in texts)


def test_stats_still_count_empty_fields_as_missing(files, tmp_path):
    left, _ = files
    profile = StatProcessor().stats(
        left, {"engine": "duckdb", "format_out": "json", "output": str(tmp_path / "s.json")}
    )
    assert profile["debug"]["fielddata"]["k"]["missing_count"] == 2
