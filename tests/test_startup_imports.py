"""Commands that run in DuckDB do not import iterabledata, pyarrow, pandas or openpyxl.

Importing them takes 0.5-1.2 s, several times the work of a command on a small file.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

HEAVY = ("iterable", "pyarrow", "pandas", "openpyxl", "polars")

RUN = """
import json, sys
from typer.main import get_command
from undatum.core import app
code = 0
try:
    get_command(app).main(sys.argv[2:], standalone_mode=False)
except SystemExit as exc:
    code = exc.code or 0
heavy = sorted(name for name in json.loads(sys.argv[1]) if name in sys.modules)
sys.__stdout__.write("\\nIMPORTED " + json.dumps({"code": code, "heavy": heavy}) + "\\n")
"""

COMMANDS = [
    ["count", "{csv}"],
    ["head", "{csv}"],
    ["headers", "{csv}"],
    ["frequency", "-f", "name", "{csv}"],
    ["uniq", "-f", "name", "{csv}"],
    ["sort", "--by", "name", "{csv}"],
    ["select", "-f", "name", "{csv}"],
    ["dedup", "-e", "duckdb", "{csv}"],
    ["sample", "-n", "1", "{csv}"],
    ["join", "{csv}", "{csv2}", "--on", "name"],
    ["fill", "{csv}", "-O", "jsonl"],
    ["slice", "{csv}", "--start", "0", "--end", "1"],
    ["stats", "{csv}"],
    ["schema", "{csv}"],
    ["quality", "{csv}"],
    ["schema-drift", "{csv}", "--baseline", "{csv2}"],
    ["convert", "{csv}", "{out}/o.jsonl"],
    ["convert", "{csv}", "{out}/o.parquet"],
    ["count", "{parquet}"],
    ["frequency", "-f", "name", "{jsonl}"],
]


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    folder = tmp_path_factory.mktemp("startup")
    (folder / "data.csv").write_text("name,city\nann,paris\nbob,rome\n", encoding="utf8")
    (folder / "data2.csv").write_text("name,age\nann,30\n", encoding="utf8")
    (folder / "data.jsonl").write_text('{"name": "ann"}\n{"name": "bob"}\n', encoding="utf8")
    import duckdb

    duckdb.sql(f"COPY (SELECT 'ann' AS name) TO '{folder / 'data.parquet'}' (FORMAT parquet)")
    return folder


@pytest.mark.parametrize("command", COMMANDS, ids=lambda command: "-".join(command[:2]))
def test_duckdb_commands_do_not_import_heavy_modules(inputs, tmp_path, command):
    paths = {
        "{csv}": str(inputs / "data.csv"),
        "{csv2}": str(inputs / "data2.csv"),
        "{jsonl}": str(inputs / "data.jsonl"),
        "{parquet}": str(inputs / "data.parquet"),
    }
    args = [paths.get(arg, arg).replace("{out}", str(tmp_path)) for arg in command]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {**os.environ, "PYTHONPATH": root + os.pathsep + os.environ.get("PYTHONPATH", "")}
    result = subprocess.run(
        [sys.executable, "-c", RUN, json.dumps(HEAVY), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=120,
    )
    lines = [line for line in result.stdout.splitlines() if line.startswith("IMPORTED ")]
    assert lines, result.stdout + result.stderr
    assert json.loads(lines[-1].removeprefix("IMPORTED ")) == {"code": 0, "heavy": []}
