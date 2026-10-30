"""Both engines produce the same records for every operation with a DuckDB form."""

from __future__ import annotations

import csv
import json

import pandas as pd
import pytest

from undatum.io import open_source
from undatum.ops import (
    DedupConfig,
    FillConfig,
    HeadConfig,
    RenameConfig,
    ReplaceConfig,
    ReverseConfig,
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
    # Duplicates for dedup: a repeated record and repeated keys.
    {"id": "2", "name": "", "note": "", "city name": "Paris", "q": "a,b"},
    {"id": "5", "name": "Alice", "note": "", "city name": "", "q": "x"},
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
    ("dedup", DedupConfig()),
    ("dedup", DedupConfig(keys=("name",))),
    ("dedup", DedupConfig(keys=("name", "city name"), keep="last")),
    ("dedup", DedupConfig(keys=("city name",), keep="last")),
    ("reverse", ReverseConfig()),
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


@pytest.mark.parametrize(("engine", "expected"), [("auto", "Python engine"), ("duckdb", "DuckDB")])
def test_reverse_needs_the_duckdb_engine(tmp_path, caplog, engine, expected):
    # DuckDB's memory would grow with the input; the Python form stays bounded.
    source = _write_input(tmp_path, "csv")
    with caplog.at_level("DEBUG", logger="undatum.ops.runner"):
        run(
            "reverse",
            ReverseConfig(),
            open_source(str(source)),
            str(tmp_path / "o.csv"),
            engine=engine,
        )
    assert any(f"reverse: {expected}" in message for message in caplog.messages)


@pytest.mark.parametrize(
    ("cfg", "expected"),
    [
        (DedupConfig(), "DuckDB engine"),
        (DedupConfig(keys=("name",), keep="last"), "DuckDB engine"),
        (DedupConfig(keys=("name",), memory_keys=2), "Python engine"),  # four names
        (DedupConfig(keys=("name",), low_memory=True), "Python engine"),
    ],
)
def test_dedup_runs_in_duckdb_when_its_keys_fit(tmp_path, caplog, cfg, expected):
    # DuckDB holds one record per key: up to memory_keys keys, as many as the Python form.
    source = _write_input(tmp_path, "csv")
    out = tmp_path / "auto.csv"
    with caplog.at_level("DEBUG", logger="undatum.ops.runner"):
        run("dedup", cfg, open_source(str(source)), str(out))
    assert any(f"dedup: {expected}" in message for message in caplog.messages)
    run("dedup", cfg, open_source(str(source)), str(tmp_path / "python.csv"), engine="python")
    assert _read_output(out) == _read_output(tmp_path / "python.csv")


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
