"""Both engines produce the same records for every operation with a DuckDB form."""

from __future__ import annotations

import csv
import json

import pandas as pd
import pytest

from undatum.io import open_source
from undatum.ops import (
    FillConfig,
    HeadConfig,
    RenameConfig,
    ReplaceConfig,
    SearchConfig,
    SelectConfig,
    SliceConfig,
    WhereConfig,
    run,
)
from undatum.ops.base import REGISTRY, Operation

ROWS = [
    {"id": "1", "name": "Alice", "note": "foo bar", "city name": "Berlin", "q": 'say "hi"'},
    {"id": "2", "name": "", "note": "", "city name": "Paris", "q": "a,b"},
    {"id": "3", "name": "Écrit", "note": "Foo FOO foo", "city name": "", "q": ""},
    {"id": "4", "name": "Dave", "note": "x.y*z", "city name": "Rome", "q": "naïve"},
]

CASES = [
    ("rename", RenameConfig(mapping={"name": "full name", "id": "key"})),
    ("rename", RenameConfig(pattern=r"\s+", replacement="_")),
    ("fill", FillConfig(fields=("name", "note"), value="N/A")),
    ("fill", FillConfig(value="-")),
    ("fill", FillConfig(fields=("missing",), value="z")),
    ("replace", ReplaceConfig(field="note", pattern="foo", replacement="X")),
    ("replace", ReplaceConfig(field="note", pattern="foo", replacement="X", global_replace=True)),
    ("replace", ReplaceConfig(field="note", pattern="x.y*", replacement="\\")),
    ("replace", ReplaceConfig(field="note", pattern="[fF]o+", replacement="Y", regex=True)),
    ("search", SearchConfig(pattern="foo", fields=("note",))),
    ("search", SearchConfig(pattern="foo", fields=("note",), ignore_case=True)),
    ("search", SearchConfig(pattern="^[A-D]")),
    ("head", HeadConfig(limit=2)),
    ("head", HeadConfig(limit=0)),
    ("slice", SliceConfig(start=1, end=3)),
    ("slice", SliceConfig(start=2)),
    ("select", SelectConfig(fields=("name", "city name"))),
    ("select", SelectConfig(filter='`id` == "2" OR `name` == "Dave"')),
    ("select", SelectConfig(fields=("id",), filter='`name` != ""')),
    ("where", WhereConfig(where="id > 2")),
    ("where", WhereConfig(where="name = 'Dave' OR \"city name\" = 'Paris'")),
    ("where", WhereConfig(add=("double = id * 2", "label = upper(name)"))),
    ("where", WhereConfig(where="id >= 2", add=("id = id + 100",))),
    ("where", WhereConfig(where="q LIKE '%,%' OR q LIKE '%\"%'")),
]


def _write_input(directory, fmt):
    path = directory / f"input.{fmt}"
    if fmt == "csv":
        with open(path, "w", newline="", encoding="utf8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(ROWS[0]))
            writer.writeheader()
            writer.writerows(ROWS)
    elif fmt == "jsonl":
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ROWS), "utf8")
    else:
        pd.DataFrame(ROWS).to_parquet(path, index=False)
    return path


def _read_output(path):
    if path.suffix == ".parquet":
        return pd.read_parquet(path).fillna("").astype(str).to_dict("records")
    if path.suffix == ".csv":
        with open(path, newline="", encoding="utf8") as handle:
            return list(csv.DictReader(handle))
    return [json.loads(line) for line in path.read_text(encoding="utf8").splitlines()]


@pytest.mark.parametrize("fmt", ["csv", "jsonl", "parquet"])
@pytest.mark.parametrize("name,cfg", CASES, ids=[f"{n}-{i}" for i, (n, _) in enumerate(CASES)])
def test_engines_agree(tmp_path, fmt, name, cfg):
    source = _write_input(tmp_path, fmt)
    outputs = {}
    for engine in ("python", "duckdb"):
        out = tmp_path / f"{engine}.{fmt}"
        run(name, cfg, open_source(str(source)), str(out), engine=engine)
        outputs[engine] = _read_output(out) if out.exists() else []
    assert outputs["duckdb"] == outputs["python"]


def test_every_sql_operation_is_covered():
    """New operations with a DuckDB form must be added to CASES."""
    covered = {name for name, _ in CASES}
    with_sql = {name for name, op in REGISTRY.items() if type(op).to_sql is not Operation.to_sql}
    assert with_sql <= covered


def test_duckdb_engine_is_used_for_readable_inputs(tmp_path, caplog):
    source = _write_input(tmp_path, "parquet")
    with caplog.at_level("DEBUG", logger="undatum.ops.runner"):
        run("rename", CASES[0][1], open_source(str(source)), str(tmp_path / "o.parquet"))
    assert any("DuckDB engine" in message for message in caplog.messages)


def test_python_engine_for_options_duckdb_cannot_honour(tmp_path, caplog):
    source = _write_input(tmp_path, "jsonl")
    with caplog.at_level("DEBUG", logger="undatum.ops.runner"):
        run(
            "head",
            HeadConfig(limit=1),
            open_source(str(source), {"flatten_nested": True}),
            str(tmp_path / "o.jsonl"),
        )
    assert any("Python engine" in message for message in caplog.messages)
