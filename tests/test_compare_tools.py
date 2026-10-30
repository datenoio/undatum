"""scripts/compare_tools.py: commands, data, checks and the report (without the other tools)."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def tools():
    spec = importlib.util.spec_from_file_location(
        "compare_tools", ROOT / "scripts" / "compare_tools.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["compare_tools"] = module
    spec.loader.exec_module(module)
    return module


def test_every_command_formats(tools, tmp_path):
    for dataset in tools.DATASETS.values():
        for task, (ext, _, commands) in tools.TASKS.items():
            for tool in commands:
                text = tools.command(task, tool, dataset, tmp_path, tmp_path / f"out.{ext}")
                assert text and "{" not in text.replace("${", ""), (task, tool, text)
                assert str(tmp_path / dataset.file) in text


def test_synthetic_data_is_deterministic(tools, tmp_path):
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    tools.write_synthetic(first, 300)
    tools.write_synthetic(second, 300)
    assert first.read_bytes() == second.read_bytes()
    assert tools.check("rows", first) == 300  # quoted line breaks are one record


def test_prepare_adds_the_price_paid_header(tools, tmp_path):
    source = tmp_path / "pp.csv"
    source.write_text('"{A}","100","2024-01-01 00:00","X","D"\n', encoding="utf8")
    tools.prepare(tmp_path / "data", 10, str(source), download=False)
    lines = (tmp_path / "data" / "price-paid-2024.csv").read_text(encoding="utf8").splitlines()
    assert lines[0].startswith("transaction_id,price,date") and len(lines) == 2
    assert (tmp_path / "data" / "property-types.csv").exists()


def test_checks(tools, tmp_path):
    (tmp_path / "n.txt").write_text("Row count: 1,234\n932214\n", encoding="utf8")
    assert tools.check("number", tmp_path / "n.txt") == 932214
    (tmp_path / "l.jsonl").write_text('{"a": 1}\n\n{"a": 2}\n', encoding="utf8")
    assert tools.check("lines", tmp_path / "l.jsonl") == 2
    assert tools.check("none", tmp_path / "l.jsonl") is None
    pq = pytest.importorskip("pyarrow.parquet")
    import pyarrow as pa

    out = tmp_path / "dir" / "out.parquet"
    out.parent.mkdir()
    pq.write_table(pa.table({"a": [1, 2, 3]}), out.parent / "synthetic.parquet")
    assert tools.check("parquet", out) == 3  # qsv writes <name>.parquet into the directory


def _results(rows):
    return {
        "created": "2026-10-29T00:00:00Z",
        "machine": {"platform": "test", "cpus": 2, "cpu": "cpu", "memory": "1 GB"},
        "tools": {"undatum": "undatum 2", "qsv": "qsv 26", "xan": "0.61"},
        "repeat": 3,
        "datasets": {"synthetic": {"title": "Synthetic", "bytes": 1_048_576, "rows": 10}},
        "results": rows,
    }


def test_markdown(tools):
    def row(tool, **kwargs):
        return {"dataset": "synthetic", "task": "select", "tool": tool, **kwargs}

    ok = {"ok": True, "seconds": 1.234, "rss_mb": 50.4}
    text = tools.markdown(
        _results(
            [
                row("undatum", check=10, **ok),
                row("qsv", check=9, **ok),
                row("xan", ok=False, error="timeout after 180 s"),
            ]
        )
    )
    assert "| select | 1.23 s · 50 MB | 1.23 s · 50 MB ⚠ | timeout |" in text
    assert "qsv select (synthetic): 9 rows, others 10" in text
    assert "10 rows, 1 MB." in text
    assert "| xan | 0.61 |" in text and "| qsv | qsv 26 |" in text  # no x.y: as given
    assert tools._version("qsv 26.0.0-jemalloc-apply;fetch") == "26.0.0"


def test_write_docs(tools, tmp_path):
    page = tmp_path / "page.md"
    page.write_text(f"intro\n{tools.BEGIN}\nold\n{tools.END}\nend\n", encoding="utf8")
    tools.write_docs(page, "new table")
    assert page.read_text(encoding="utf8") == f"intro\n{tools.BEGIN}\nnew table\n{tools.END}\nend\n"


def test_run_with_undatum(tools, tmp_path):
    shims = tmp_path / "bin"
    shims.mkdir()
    shim = shims / "undatum"
    shim.write_text(
        f'#!/bin/bash\nPYTHONPATH="{ROOT}" exec "{sys.executable}" -m undatum "$@"\n',
        encoding="utf8",
    )
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    data = tmp_path / "data"
    tools.prepare(data, 200, None, download=False)
    results = tools.run(
        data, [str(shims)], 1, 120, 60, ["undatum"], ["count", "select", "frequency", "to-jsonl"]
    )
    by_task = {row["task"]: row for row in results["results"]}
    assert set(by_task) == {"count", "select", "frequency", "to-jsonl"}
    assert all(row["ok"] for row in by_task.values()), by_task
    assert by_task["count"]["check"] == 200 and by_task["to-jsonl"]["check"] == 200
    assert 0 < by_task["frequency"]["check"] <= 200  # distinct cities
    assert results["datasets"]["synthetic"]["rows"] == 200
    json.dumps(results)
    assert os.environ.get("UNDATUM_CACHE") != "0"  # set only for the measured processes


def test_timeout_stops_the_whole_pipeline(tools, tmp_path):
    late = tmp_path / "late"
    shell = f"(sleep 1; touch {late}) | cat"
    result = tools.measure(shell, dict(os.environ), 0.3, tmp_path / "run" / "out.txt")
    assert result == {"ok": False, "error": "timeout after 0 s"}
    time.sleep(1.5)
    assert not late.exists()


def test_tools_take_turns(tools, tmp_path):
    log = tmp_path / "order.log"
    jobs = {name: (f"echo {name} >> {log}", tmp_path / name / "out.txt") for name in "ab"}
    jobs["c"] = ("exit 3", tmp_path / "c" / "out.txt")
    results = tools.measure_task(jobs, dict(os.environ), 3, 10, 60)
    assert log.read_text(encoding="utf8").split() == ["a", "b", "a", "b", "a", "b"]
    assert len(results["a"]["runs"]) == 3
    assert results["a"]["seconds"] == min(results["a"]["runs"])
    assert results["c"] == {"ok": False, "error": "exit 3"}
    slow = tools.measure_task({"a": jobs["a"]}, dict(os.environ), 3, 10, 0)
    assert len(slow["a"]["runs"]) == 1  # longer than --slow: one run


def test_combine_keeps_the_fastest_run(tools):
    def row(tool, **kwargs):
        return {"dataset": "synthetic", "task": "select", "tool": tool, **kwargs}

    first = _results(
        [
            row("undatum", ok=True, seconds=2.0, runs=[2.0, 2.5], rss_mb=50, check=10),
            row("xan", ok=False, error="timeout after 180 s"),
            row("qsv", ok=False, error="timeout after 180 s"),
        ]
    )
    second = _results(
        [
            row("undatum", ok=True, seconds=0.5, runs=[0.5], rss_mb=40, check=10),
            row("xan", ok=True, seconds=9.0, runs=[9.0], rss_mb=12, check=10),
            row("qsv", ok=False, error="timeout after 180 s"),
        ]
    )
    combined = tools.combine([first, second])
    by_tool = {r["tool"]: r for r in combined["results"]}
    assert by_tool["undatum"]["seconds"] == 0.5 and by_tool["undatum"]["rss_mb"] == 50
    assert by_tool["undatum"]["runs"] == [2.0, 2.5, 0.5]
    assert by_tool["xan"]["seconds"] == 9.0 and not by_tool["qsv"]["ok"]
    assert "fastest of up to 6 runs in 2 sessions" in tools.markdown(combined)
    assert tools.combine([first]) is first
