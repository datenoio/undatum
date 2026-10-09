"""Output contract: every record-writing command writes every core output format.

Before 1.7.1, thirteen commands created an empty file and exited with code 0
for any output format other than csv/json/jsonl/bson. This suite runs each
command through the CLI for each core output format, reads the result back and
checks the row count, and checks that a non-writable format fails without
leaving a file behind.
"""

import csv
import gzip
import json
import os

import pytest
from typer.testing import CliRunner

from undatum.core import app

runner = CliRunner()

INPUT_CSV = "a,b,tags\n1,x,p;q\n2,y,r\n3,z,s\n1,x,p;q\n"
SECOND_CSV = "a,c\n1,c1\n2,c2\n"

# (command id, argv template, expected row count or None for "at least one row")
COMMANDS = [
    ("rename", ["rename", "{in}", "--map", "a:id"], 4),
    ("fill", ["fill", "{in}", "--value", "0"], 4),
    ("replace", ["replace", "{in}", "--field", "b", "--pattern", "x", "--replacement", "w"], 4),
    ("enum", ["enum", "{in}", "--field", "n"], 4),
    ("head", ["head", "{in}", "--n", "2"], 2),
    ("tail", ["tail", "{in}", "--n", "2"], 2),
    ("reverse", ["reverse", "{in}"], 4),
    ("search", ["search", "{in}", "--pattern", "x"], 2),
    ("explode", ["explode", "{in}", "--field", "tags", "--separator", ";"], 6),
    ("join", ["join", "{in}", "{in2}", "--on", "a"], 3),
    ("cat", ["cat", "{in}", "{in2}"], 6),
    ("fixlengths", ["fixlengths", "{in}"], 4),
    ("transpose", ["transpose", "{in}"], None),
    ("sort", ["sort", "{in}", "--by", "a"], 4),
    ("dedup", ["dedup", "{in}"], 3),
    ("sample", ["sample", "{in}", "--n", "2"], 2),
    ("slice", ["slice", "{in}", "--start", "0", "--end", "1"], None),
    ("select", ["select", "{in}", "--fields", "a"], 4),
    ("exclude", ["exclude", "{in}", "{in2}", "--on", "a"], 1),
    ("fmt", ["fmt", "{in}"], 4),
    ("uniq", ["uniq", "{in}", "--fields", "a"], 3),
    ("frequency", ["frequency", "{in}", "--fields", "a"], 3),
]

WRITABLE_FORMATS = ["csv", "tsv", "jsonl", "json", "parquet", "csv.gz"]


def _read_back(path: str) -> list[dict]:
    if path.endswith(".tsv"):
        with open(path, newline="", encoding="utf8") as handle:
            return list(csv.DictReader(handle, delimiter="\t"))
    if path.endswith(".csv.gz"):
        with gzip.open(path, "rt", newline="", encoding="utf8") as handle:
            return list(csv.DictReader(handle))
    if path.endswith(".csv"):
        with open(path, newline="", encoding="utf8") as handle:
            return list(csv.DictReader(handle))
    if path.endswith(".json"):
        with open(path, encoding="utf8") as handle:
            data = json.load(handle)
        return data if isinstance(data, list) else [data]
    from iterable.helpers.detect import open_iterable

    iterable = open_iterable(path)
    try:
        return list(iterable)
    finally:
        iterable.close()


@pytest.fixture
def inputs(tmp_path):
    first = tmp_path / "input.csv"
    second = tmp_path / "second.csv"
    first.write_text(INPUT_CSV, encoding="utf8")
    second.write_text(SECOND_CSV, encoding="utf8")
    return str(first), str(second)


def _argv(template, inputs, output):
    mapping = {"{in}": inputs[0], "{in2}": inputs[1]}
    return [mapping.get(part, part) for part in template] + ["--output", output]


@pytest.mark.parametrize("fmt", WRITABLE_FORMATS)
@pytest.mark.parametrize("name,template,expected", COMMANDS, ids=[c[0] for c in COMMANDS])
def test_command_writes_format(tmp_path, inputs, name, template, expected, fmt):
    output = str(tmp_path / f"out.{fmt}")
    result = runner.invoke(app, _argv(template, inputs, output))
    assert result.exit_code == 0, result.output
    assert os.path.exists(output), f"{name} did not create {fmt} output"
    assert os.path.getsize(output) > 0, f"{name} wrote an empty {fmt} file"
    rows = _read_back(output)
    if expected is None:
        assert rows, f"{name} wrote no rows to {fmt}"
    else:
        assert len(rows) == expected, f"{name} → {fmt}: {rows}"


@pytest.mark.parametrize("name,template,expected", COMMANDS, ids=[c[0] for c in COMMANDS])
def test_non_writable_format_fails_without_file(tmp_path, inputs, name, template, expected):
    from iterable.helpers.capabilities import supports_write

    # xlsx became writable in newer iterabledata; xls stays read-only.
    fmt = next((f for f in ("xlsx", "xls") if supports_write(f) is False), None)
    if fmt is None:
        pytest.skip("no read-only spreadsheet format in this iterabledata version")
    output = str(tmp_path / f"out.{fmt}")
    result = runner.invoke(app, _argv(template, inputs, output))
    assert result.exit_code != 0, f"{name} accepted a non-writable format"
    assert not os.path.exists(output), f"{name} left {output} behind"
    leftovers = [p for p in os.listdir(tmp_path) if p.startswith(".undatum-tmp-")]
    assert not leftovers
