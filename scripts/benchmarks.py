#!/usr/bin/env python3
"""Wall-time and peak-memory benchmarks of undatum commands.

Every command runs in its own process; wall time is the median of ``--repeat`` runs and
peak memory is the largest resident set size the process reached (``os.wait4``).

Usage::

    python scripts/benchmarks.py generate --tier 100k --dir bench-data
    python scripts/benchmarks.py run --tier 100k --data bench-data --out results.json
    python scripts/benchmarks.py check results.json
    # Pull requests: measure both checkouts in one run, then compare.
    python scripts/benchmarks.py run --tier 100k --data bench-data \\
        --python base=../base/.venv/bin/python --python head=.venv/bin/python --out pr.json
    python scripts/benchmarks.py compare pr.json --base base --head head
    # Nightly history.
    python scripts/benchmarks.py history results.json --file history.jsonl --svg history.svg

Budgets per tier live in ``tests/benchmarks/budgets.toml``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
BUDGETS = ROOT / "tests" / "benchmarks" / "budgets.toml"
TIERS = {"tiny": 2_000, "100k": 100_000, "1m": 1_000_000}

# name -> argv after ``python -m undatum``. {csv}, {jsonl}, {parquet}: inputs; {out}: a
# fresh output directory per run.
SUITE: dict[str, list[str]] = {
    "help": ["--help"],
    "version": ["--version"],
    "head": ["head", "{csv}", "-n", "10"],
    "count": ["count", "{csv}"],
    "count-jsonl": ["count", "{jsonl}"],
    "headers": ["headers", "{csv}"],
    "rename": ["rename", "{csv}", "--map", "name:label", "-o", "{out}/r.csv"],
    "fill": ["fill", "{csv}", "--fields", "city", "--value", "z", "-o", "{out}/f.csv"],
    "dedup": ["dedup", "{csv}", "--key-fields", "city", "-o", "{out}/d.csv"],
    "select": ["select", "{csv}", "-f", "id,amount", "-o", "{out}/s.csv"],
    "sort": ["sort", "{csv}", "--by", "amount", "-o", "{out}/o.csv"],
    "frequency": ["frequency", "{csv}", "-f", "city"],
    "uniq": ["uniq", "{csv}", "-f", "city"],
    "stats": ["stats", "{csv}"],
    "schema": ["schema", "{csv}"],
    "sql": ["sql", "SELECT city, count(*) AS n FROM data GROUP BY city", "{csv}"],
    "convert-parquet": ["convert", "{csv}", "{out}/c.parquet"],
    "convert-jsonl": ["convert", "{parquet}", "{out}/c.jsonl"],
}


# --- datasets ----------------------------------------------------------------------------


def generate(tier: str, directory: Path) -> dict[str, Path]:
    """Write ``bench.csv``, ``bench.jsonl`` and ``bench.parquet`` with ``TIERS[tier]`` rows.

    Values are derived from the row number, so every run produces the same files.
    """
    import duckdb

    rows = TIERS[tier]
    directory.mkdir(parents=True, exist_ok=True)
    query = f"""
        SELECT
            i AS id,
            'name' || (i * 7919 % 1000) AS name,
            round((i * 2654435761 % 1000000) / 100.0, 2) AS amount,
            'city' || (i % 50) AS city,
            DATE '2020-01-01' + CAST(i % 1500 AS INTEGER) AS day,
            CASE WHEN i % 97 = 0 THEN 'say "hi", twice' ELSE 'plain text ' || (i % 13) END
                AS comment,
            md5(CAST(i AS VARCHAR)) AS code,
            repeat('lorem ipsum ', CAST(1 + i % 8 AS INTEGER)) AS notes
        FROM range({rows}) t(i)
    """
    paths = {
        "csv": directory / "bench.csv",
        "jsonl": directory / "bench.jsonl",
        "parquet": directory / "bench.parquet",
    }
    conn = duckdb.connect()
    conn.execute("SET threads = 1")  # stable row order
    conn.execute(f"COPY ({query}) TO '{paths['csv']}' (HEADER, DELIMITER ',')")
    conn.execute(f"COPY ({query}) TO '{paths['jsonl']}' (FORMAT JSON)")
    conn.execute(f"COPY ({query}) TO '{paths['parquet']}' (FORMAT PARQUET)")
    conn.close()
    return paths


# --- measuring ---------------------------------------------------------------------------


def _peak_mb(usage: Any) -> float:
    # ru_maxrss is in bytes on macOS and in KiB on Linux.
    scale = 1 if sys.platform == "darwin" else 1024
    return round(usage.ru_maxrss * scale / 1_048_576, 1)


def measure(python: str, argv: list[str], repeat: int = 3) -> dict[str, Any]:
    """Run ``python -m undatum *argv`` ``repeat`` times; median seconds, max RSS in MB."""
    seconds: list[float] = []
    peaks: list[float] = []
    for _ in range(repeat):
        with (
            tempfile.TemporaryDirectory(prefix="undatum-bench-") as out,
            tempfile.TemporaryFile() as err,
        ):
            args = [a.replace("{out}", out) for a in argv]
            start = time.perf_counter()
            proc = subprocess.Popen(
                [python, "-m", "undatum", *args],
                stdout=subprocess.DEVNULL,
                stderr=err,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            )
            _, status, usage = os.wait4(proc.pid, 0)
            elapsed = time.perf_counter() - start
            proc.returncode = os.waitstatus_to_exitcode(status)
            if proc.returncode != 0:
                err.seek(0)
                message = err.read().decode("utf8", "replace").strip().splitlines()
                return {"ok": False, "error": message[-1] if message else f"exit {proc.returncode}"}
        seconds.append(elapsed)
        peaks.append(_peak_mb(usage))
    return {
        "ok": True,
        "seconds": round(statistics.median(seconds), 3),
        "rss_mb": max(peaks),
        "runs": [round(s, 3) for s in seconds],
    }


def run(
    tier: str,
    data: Path,
    pythons: dict[str, str],
    repeat: int = 3,
    only: list[str] | None = None,
) -> dict[str, Any]:
    """Measure the suite for each interpreter; commands are interleaved across them."""
    inputs = {
        "{csv}": str(data / "bench.csv"),
        "{jsonl}": str(data / "bench.jsonl"),
        "{parquet}": str(data / "bench.parquet"),
    }
    missing = [path for path in inputs.values() if not Path(path).exists()]
    if missing:
        raise SystemExit(f"missing datasets ({', '.join(missing)}); run `generate` first")
    results: dict[str, dict[str, Any]] = {label: {} for label in pythons}
    for name, template in SUITE.items():
        if only and name not in only:
            continue
        argv = [inputs.get(a, a) for a in template]
        for label, python in pythons.items():
            result = measure(python, argv, repeat)
            results[label][name] = result
            shown = (
                f"{result['seconds']:.3f} s {result['rss_mb']:.0f} MB"
                if result["ok"]
                else f"failed: {result['error']}"
            )
            print(f"{label:>6} {name:<16} {shown}", file=sys.stderr)
    return {
        "tier": tier,
        "rows": TIERS[tier],
        "repeat": repeat,
        "created": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "platform": platform.platform(),
        "commit": os.environ.get("GITHUB_SHA") or _git_commit(),
        "runs": results,
    }


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


# --- budgets and comparison --------------------------------------------------------------


def load_budgets(path: Path = BUDGETS) -> dict[str, Any]:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10 (tomli comes with pytest)
        import tomli as tomllib  # type: ignore[no-redef]
    with open(path, "rb") as handle:
        return tomllib.load(handle)


def check_budgets(results: dict[str, Any], budgets: dict[str, Any], label: str) -> list[str]:
    """Commands over their tier budget, failed commands, and broken ``faster`` relations."""
    tier = results["tier"]
    limits = budgets.get("tier", {}).get(tier, {})
    measured = results["runs"][label]
    problems = []
    for name, result in measured.items():
        if not result["ok"]:
            problems.append(f"{name}: failed ({result['error']})")
            continue
        limit = limits.get(name)
        if not limit:
            continue
        if result["seconds"] > limit["seconds"]:
            problems.append(f"{name}: {result['seconds']:.2f} s > budget {limit['seconds']} s")
        if result["rss_mb"] > limit["rss_mb"]:
            problems.append(f"{name}: {result['rss_mb']:.0f} MB > budget {limit['rss_mb']} MB")
    for fast, slow in budgets.get("faster", []):
        a, b = measured.get(fast), measured.get(slow)
        if a and b and a["ok"] and b["ok"] and a["seconds"] > b["seconds"]:
            problems.append(
                f"{fast} ({a['seconds']:.2f} s) should be faster than {slow} ({b['seconds']:.2f} s)"
            )
    return problems


def compare(
    results: dict[str, Any],
    base: str,
    head: str,
    threshold: float = 0.2,
    min_seconds: float = 0.1,
    min_mb: float = 15.0,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Rows of a base/head comparison and the regressions above ``threshold``.

    Differences below ``min_seconds`` / ``min_mb`` are noise and never count.
    """
    rows = []
    regressions = []
    for name in results["runs"][head]:
        new = results["runs"][head][name]
        old = results["runs"].get(base, {}).get(name)
        row: dict[str, Any] = {"command": name, "base": old, "head": new, "flags": []}
        if new["ok"] and old and old["ok"]:
            for key, floor, unit in (("seconds", min_seconds, "s"), ("rss_mb", min_mb, "MB")):
                before, after = old[key], new[key]
                if after > before * (1 + threshold) and after - before > floor:
                    row["flags"].append(key)
                    regressions.append(
                        f"{name}: {key} {before:g} -> {after:g} {unit} (+{after / before - 1:.0%})"
                    )
        elif not new["ok"] and old and old["ok"]:
            row["flags"].append("failed")
            regressions.append(f"{name}: failed ({new['error']})")
        rows.append(row)
    return rows, regressions


def _cell(result: dict[str, Any] | None) -> str:
    if not result:
        return "—"
    if not result["ok"]:
        return "failed"
    return f"{result['seconds']:.2f} s / {result['rss_mb']:.0f} MB"


def markdown(rows: list[dict[str, Any]], tier: str, base: str, head: str) -> str:
    lines = [
        f"### Benchmarks ({tier} rows)",
        "",
        f"| Command | {base} | {head} | Change |",
        "|---|---|---|---|",
    ]
    for row in rows:
        old, new = row["base"], row["head"]
        change = ""
        if old and new and old["ok"] and new["ok"] and old["seconds"]:
            change = f"{new['seconds'] / old['seconds'] - 1:+.0%} time"
            if old["rss_mb"]:
                change += f", {new['rss_mb'] / old['rss_mb'] - 1:+.0%} memory"
        if row["flags"]:
            change += " **regression**"
        lines.append(f"| {row['command']} | {_cell(old)} | {_cell(new)} | {change} |")
    return "\n".join(lines)


# --- history -----------------------------------------------------------------------------


def append_history(results: dict[str, Any], label: str, history: Path) -> list[dict[str, Any]]:
    """Append one summary line to ``history`` (JSON Lines) and return all entries."""
    entry = {
        "created": results["created"],
        "commit": results["commit"],
        "tier": results["tier"],
        "results": {
            name: {"seconds": r["seconds"], "rss_mb": r["rss_mb"]}
            for name, r in results["runs"][label].items()
            if r["ok"]
        },
    }
    with open(history, "a", encoding="utf8") as handle:
        handle.write(json.dumps(entry) + "\n")
    with open(history, encoding="utf8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def history_svg(entries: list[dict[str, Any]], last: int = 60) -> str:
    """Small multiples: seconds (solid) and peak MB (dashed) per command over time."""
    entries = entries[-last:]
    names = list(dict.fromkeys(name for e in entries for name in e["results"]))
    columns, width, height, pad = 3, 300, 130, 28
    rows = (len(names) + columns - 1) // columns or 1
    total_w, total_h = columns * width, rows * height + 30
    title = "undatum nightly benchmarks"
    if entries:
        title += f" ({entries[-1]['tier']} rows, seconds solid, MB dashed)"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w} {total_h}" '
        f'width="{total_w}" height="{total_h}" font-family="sans-serif" font-size="11">',
        f'<rect width="{total_w}" height="{total_h}" fill="#fff"/>',
        f'<text x="8" y="18" font-size="13" font-weight="bold">{escape(title)}</text>',
    ]
    if not entries:
        parts.append('<text x="8" y="44">No nightly results yet.</text>')
    for index, name in enumerate(names):
        x0 = (index % columns) * width
        y0 = 30 + (index // columns) * height
        points = [(i, e["results"].get(name)) for i, e in enumerate(entries)]
        points = [(i, r) for i, r in points if r]
        latest = points[-1][1]
        parts.append(
            f'<text x="{x0 + 8}" y="{y0 + 14}">{escape(name)}: {latest["seconds"]:.2f} s, '
            f"{latest['rss_mb']:.0f} MB</text>"
        )
        parts.append(
            f'<rect x="{x0 + 8}" y="{y0 + 20}" width="{width - 16}" height="{height - pad - 8}" '
            'fill="none" stroke="#ddd"/>'
        )
        for key, style in (
            ("seconds", 'stroke="#2563eb"'),
            ("rss_mb", 'stroke="#d97706" stroke-dasharray="4 3"'),
        ):
            top = max(r[key] for _, r in points) or 1
            span = max(len(entries) - 1, 1)
            coords = " ".join(
                f"{x0 + 8 + (width - 16) * i / span:.1f},"
                f"{y0 + 20 + (height - pad - 8) * (1 - r[key] / top * 0.9):.1f}"
                for i, r in points
            )
            parts.append(f'<polyline fill="none" {style} stroke-width="1.5" points="{coords}"/>')
    parts.append("</svg>")
    return "\n".join(parts)


# --- command line ------------------------------------------------------------------------


def _pythons(values: list[str] | None) -> dict[str, str]:
    if not values:
        return {"head": sys.executable}
    pythons = {}
    for value in values:
        label, sep, path = value.partition("=")
        pythons[label if sep else "head"] = path if sep else label
    return pythons


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="action", required=True)

    p = sub.add_parser("generate", help="write the reference datasets")
    p.add_argument("--tier", choices=TIERS, default="100k")
    p.add_argument("--dir", type=Path, required=True)

    p = sub.add_parser("run", help="measure the suite")
    p.add_argument("--tier", choices=TIERS, default="100k")
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--python", action="append", help="LABEL=PATH (repeatable)")
    p.add_argument("--repeat", type=int, default=3)
    p.add_argument("--only", help="comma-separated command names")
    p.add_argument("--out", type=Path, required=True)

    p = sub.add_parser("check", help="fail when a command exceeds its budget")
    p.add_argument("results", type=Path)
    p.add_argument("--label", default=None)
    p.add_argument("--budgets", type=Path, default=BUDGETS)

    p = sub.add_parser("compare", help="fail on regressions of head against base")
    p.add_argument("results", type=Path)
    p.add_argument("--base", default="base")
    p.add_argument("--head", default="head")
    p.add_argument("--threshold", type=float, default=0.2)
    p.add_argument("--budgets", type=Path, default=BUDGETS)

    p = sub.add_parser("history", help="append results to a history file and draw it")
    p.add_argument("results", type=Path)
    p.add_argument("--label", default=None)
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--svg", type=Path)

    args = parser.parse_args(argv)
    if args.action == "generate":
        for path in generate(args.tier, args.dir).values():
            print(path)
        return 0
    if args.action == "run":
        only = args.only.split(",") if args.only else None
        results = run(args.tier, args.data, _pythons(args.python), args.repeat, only)
        args.out.write_text(json.dumps(results, indent=2), encoding="utf8")
        return 0

    results = json.loads(args.results.read_text(encoding="utf8"))
    if args.action == "check":
        label = args.label or next(iter(results["runs"]))
        problems = check_budgets(results, load_budgets(args.budgets), label)
        for problem in problems:
            print(f"over budget: {problem}")
        return 1 if problems else 0
    if args.action == "compare":
        rows, regressions = compare(results, args.base, args.head, args.threshold)
        print(markdown(rows, results["tier"], args.base, args.head))
        problems = regressions + check_budgets(results, load_budgets(args.budgets), args.head)
        if problems:
            print("\n**Failed:**\n")
            print("\n".join(f"- {problem}" for problem in problems))
        return 1 if problems else 0
    if args.action == "history":
        label = args.label or next(iter(results["runs"]))
        entries = append_history(results, label, args.file)
        if args.svg:
            args.svg.write_text(history_svg(entries), encoding="utf8")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
