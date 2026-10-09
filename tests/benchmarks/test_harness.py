"""The benchmark harness (scripts/benchmarks.py) on a tiny dataset."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("benchmarks", ROOT / "scripts" / "benchmarks.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["benchmarks"] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop("benchmarks", None)


def _result(seconds, rss_mb, ok=True):
    return {"ok": ok, "seconds": seconds, "rss_mb": rss_mb, "runs": [seconds]}


def test_budgets_cover_the_suite(bench):
    budgets = bench.load_budgets()
    for tier in ("100k", "1m"):
        assert set(budgets["tier"][tier]) == set(bench.SUITE), tier
    for fast, slow in budgets["faster"]:
        assert fast in bench.SUITE and slow in bench.SUITE


def test_generate_is_deterministic(bench, tmp_path):
    first = bench.generate("tiny", tmp_path / "a")
    second = bench.generate("tiny", tmp_path / "b")
    for fmt in ("csv", "jsonl"):
        assert first[fmt].read_bytes() == second[fmt].read_bytes()
    lines = first["csv"].read_text(encoding="utf8").splitlines()
    assert len(lines) == bench.TIERS["tiny"] + 1
    assert lines[0] == "id,name,amount,city,day,comment,code,notes"


def test_run_measures_commands(bench, tmp_path):
    bench.generate("tiny", tmp_path)
    results = bench.run("tiny", tmp_path, {"head": sys.executable}, repeat=1, only=["count"])
    count = results["runs"]["head"]["count"]
    assert count["ok"], count
    assert count["seconds"] > 0 and count["rss_mb"] > 10
    assert results["rows"] == bench.TIERS["tiny"]


def test_failed_command_is_reported(bench):
    result = bench.measure(sys.executable, ["count", "/does/not/exist.csv"], repeat=1)
    assert not result["ok"] and result["error"]


def test_check_budgets(bench):
    results = {
        "tier": "100k",
        "runs": {"head": {"count": _result(0.9, 50), "sort": _result(0.5, 400)}},
    }
    budgets = {
        "tier": {
            "100k": {"count": {"seconds": 1, "rss_mb": 100}, "sort": {"seconds": 1, "rss_mb": 300}}
        },
        "faster": [["count", "sort"]],
    }
    problems = bench.check_budgets(results, budgets, "head")
    assert any("sort: 400 MB > budget 300 MB" in p for p in problems)
    assert any("count (0.90 s) should be faster than sort" in p for p in problems)
    assert not any(p.startswith("count:") for p in problems)


def test_compare_flags_regressions_above_noise(bench):
    results = {
        "tier": "100k",
        "runs": {
            "base": {
                "rename": _result(1.0, 150),
                "head": _result(0.20, 80),
                "fill": _result(1.0, 150),
            },
            "head": {
                "rename": _result(1.0, 220),  # +47% memory: regression
                "head": _result(0.28, 80),  # +40% but only 0.08 s: noise
                "fill": _result(1.0, 150, ok=False) | {"error": "boom"},
            },
        },
    }
    rows, regressions = bench.compare(results, "base", "head")
    assert any(r.startswith("rename: rss_mb") for r in regressions)
    assert any(r.startswith("fill: failed") for r in regressions)
    assert not any(r.startswith("head:") for r in regressions)
    table = bench.markdown(rows, "100k", "base", "head")
    assert "| rename |" in table and "**regression**" in table


def test_history_and_chart(bench, tmp_path):
    history = tmp_path / "history.jsonl"
    for seconds in (1.0, 1.2):
        results = {
            "tier": "1m",
            "created": "2026-10-08T00:00:00+00:00",
            "commit": "abc",
            "runs": {"master": {"count": _result(seconds, 100), "sort": _result(2, 300)}},
        }
        entries = bench.append_history(results, "master", history)
    assert len(entries) == 2
    assert json.loads(history.read_text().splitlines()[-1])["results"]["count"]["seconds"] == 1.2
    svg = bench.history_svg(entries)
    assert svg.startswith("<svg") and svg.count("<polyline") == 4
    assert "No nightly results yet" in bench.history_svg([])
