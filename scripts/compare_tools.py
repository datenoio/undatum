#!/usr/bin/env python3
"""Compare undatum with csvkit, Miller, qsv, xan and the DuckDB CLI on the same tasks.

Every command runs in its own process (``bash -c``, so tools can redirect their output);
wall time is the fastest of ``--repeat`` runs (other programs on the machine only slow a run
down) and peak memory the largest resident set size (``os.wait4``). After each run the output
is checked (rows written, rows counted), so a tool that computes a different answer is flagged,
not ranked.

Usage::

    # Synthetic data (1M rows); --price-paid adds HM Land Registry Price Paid 2024
    # (162.6 MB, Open Government Licence v3), from a local copy or --download
    python scripts/compare_tools.py prepare --dir bench-compare --price-paid pp-2024.csv
    python scripts/compare_tools.py run --dir bench-compare --out results.json \\
        --path ~/csvkit/bin --repeat 5
    python scripts/compare_tools.py markdown results.json \\
        --docs docs/docs/getting-started/benchmarks.md

Tools are found on ``PATH`` (``--path`` adds directories first): ``undatum``, ``csvkit``
(``csvcut``, ``csvsql``, ...), ``mlr``, ``qsv``, ``xan`` and ``duckdb``. Missing ones are
skipped. ``UNDATUM_CACHE=0`` keeps undatum from reusing cached results between runs.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import platform
import random
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PRICE_PAID_URL = (
    "http://prod2.publicdata.landregistry.gov.uk.s3-website-eu-west-1.amazonaws.com/pp-2024.csv"
)
PRICE_PAID_COLUMNS = (
    "transaction_id,price,date,postcode,property_type,old_new,duration,paon,saon,street,"
    "locality,town,district,county,ppd_category,record_status"
)
PROPERTY_TYPES = {
    "D": "Detached",
    "S": "Semi-detached",
    "T": "Terraced",
    "F": "Flat or maisonette",
    "O": "Other",
}
SEED = 20261029
BEGIN = "<!-- BEGIN GENERATED: comparison -->"
END = "<!-- END GENERATED: comparison -->"


@dataclass(frozen=True)
class Dataset:
    """A data file and the columns the tasks use."""

    file: str
    lookup: str  # small table joined on ``key``
    key: str
    select: str  # three columns, comma-separated
    number: str  # numeric column for filter and sort
    threshold: str
    group: str  # column for frequency and dedup
    title: str


DATASETS = {
    "synthetic": Dataset(
        file="synthetic.csv",
        lookup="categories.csv",
        key="category",
        select="id,city,amount",
        number="amount",
        threshold="5000",
        group="city",
        title="Synthetic",
    ),
    "price-paid": Dataset(
        file="price-paid-2024.csv",
        lookup="property-types.csv",
        key="property_type",
        select="price,date,town",
        number="price",
        threshold="500000",
        group="town",
        title="UK Price Paid 2024",
    ),
}

TOOLS = {
    "undatum": ("undatum", "undatum --version"),
    "csvkit": ("csvcut", "csvcut --version"),
    "miller": ("mlr", "mlr --version"),
    "qsv": ("qsv", "qsv --version"),
    "xan": ("xan", "xan --version"),
    "duckdb": ("duckdb", "duckdb --version"),
}


def _duckdb(query: str, out: str = "{out}", fmt: str = "FORMAT csv, HEADER") -> str:
    return f"duckdb -c \"COPY ({query}) TO '{out}' ({fmt})\""


READ = "read_csv('{data}')"

# task -> (output extension, check, {tool: command}); a missing tool has no such command.
TASKS: dict[str, tuple[str, str, dict[str, str]]] = {
    "count": (
        "txt",
        "number",
        {
            "undatum": "undatum count {data} > {out}",
            "csvkit": "csvstat --count {data} > {out}",
            "miller": "mlr --icsv --onidx count {data} > {out}",
            "qsv": "qsv count {data} > {out}",
            "xan": "xan count {data} > {out}",
            "duckdb": f'duckdb -csv -noheader -c "SELECT count(*) FROM {READ}" > {{out}}',
        },
    ),
    "select": (
        "csv",
        "rows",
        {
            "undatum": "undatum select {data} --fields {select} --output {out}",
            "csvkit": "csvcut -c {select} {data} > {out}",
            "miller": "mlr --csv cut -o -f {select} {data} > {out}",
            "qsv": "qsv select {select} {data} -o {out}",
            "xan": "xan select {select} {data} -o {out}",
            "duckdb": _duckdb(f"SELECT {{select}} FROM {READ}"),
        },
    ),
    "filter": (
        "csv",
        "rows",
        {
            "undatum": 'undatum select {data} --where "{number} > {threshold}" --output {out}',
            "csvkit": (
                'csvsql --tables data --query "SELECT * FROM data WHERE {number} > {threshold}" '
                "{data} > {out}"
            ),
            "miller": "mlr --csv filter '${number} > {threshold}' {data} > {out}",
            "qsv": 'qsv sqlp {data} "SELECT * FROM _t_1 WHERE {number} > {threshold}" -o {out}',
            "xan": "xan filter '{number} > {threshold}' {data} -o {out}",
            "duckdb": _duckdb(f"SELECT * FROM {READ} WHERE {{number}} > {{threshold}}"),
        },
    ),
    "sort": (
        "csv",
        "rows",
        {
            "undatum": "undatum sort {data} --by {number} --numeric {number} --desc --output {out}",
            "csvkit": "csvsort -c {number} -r {data} > {out}",
            "miller": "mlr --csv sort -nr {number} {data} > {out}",
            "qsv": "qsv sort -s {number} -N -R {data} -o {out}",
            "xan": "xan sort -s {number} -N -R {data} -o {out}",
            "duckdb": _duckdb(f"SELECT * FROM {READ} ORDER BY {{number}} DESC"),
        },
    ),
    "frequency": (
        "csv",
        "rows",
        {
            "undatum": "undatum frequency {data} --fields {group} --output {out}",
            "csvkit": (
                'csvsql --tables data --query "SELECT {group}, COUNT(*) AS count FROM data '
                'GROUP BY {group}" {data} > {out}'
            ),
            "miller": "mlr --csv count-distinct -f {group} {data} > {out}",
            "qsv": "qsv frequency -s {group} --limit 0 {data} -o {out}",
            "xan": "xan frequency -s {group} -l 0 {data} -o {out}",
            "duckdb": _duckdb(
                f"SELECT {{group}}, count(*) AS count FROM {READ} GROUP BY {{group}}"
            ),
        },
    ),
    "stats": (
        "txt",
        "none",
        {
            "undatum": "undatum stats {data} --json > {out}",
            "csvkit": "csvstat {data} > {out}",
            "miller": "mlr --icsv --opprint summary {data} > {out}",
            "qsv": "qsv stats {data} -o {out}",
            "xan": "xan stats {data} -o {out}",
            "duckdb": f'duckdb -c "SUMMARIZE SELECT * FROM {READ}" > {{out}}',
        },
    ),
    "dedup": (
        "csv",
        "rows",
        {
            "undatum": "undatum dedup {data} --key-fields {group} --output {out}",
            "miller": "mlr --csv head -n 1 -g {group} {data} > {out}",
            "qsv": "qsv dedup -s {group} {data} -o {out}",
            "xan": "xan dedup -s {group} {data} -o {out}",
            "duckdb": _duckdb(
                f"SELECT * FROM {READ} QUALIFY row_number() OVER (PARTITION BY {{group}}) = 1"
            ),
        },
    ),
    "join": (
        "csv",
        "rows",
        {
            "undatum": "undatum join {data} {lookup} --on {key} --output {out}",
            "csvkit": "csvjoin -c {key} {data} {lookup} > {out}",
            "miller": "mlr --csv join -j {key} -f {lookup} {data} > {out}",
            "qsv": "qsv join {key} {data} {key} {lookup} -o {out}",
            "xan": "xan join {key} {data} {key} {lookup} -o {out}",
            "duckdb": _duckdb(
                f"SELECT * FROM {READ} AS d JOIN read_csv('{{lookup}}') AS l USING ({{key}})"
            ),
        },
    ),
    "to-jsonl": (
        "jsonl",
        "lines",
        {
            "undatum": "undatum convert {data} {out}",
            "csvkit": "csvjson --stream {data} > {out}",
            "miller": "mlr --icsv --ojsonl cat {data} > {out}",
            "qsv": "qsv tojsonl {data} -o {out}",
            "xan": "xan to jsonl {data} -o {out}",
            "duckdb": _duckdb(f"SELECT * FROM {READ}", fmt="FORMAT json"),
        },
    ),
    "to-parquet": (
        "parquet",
        "parquet",
        {
            "undatum": "undatum convert {data} {out}",
            "qsv": "qsv to parquet {out_dir} {data}",
            "duckdb": _duckdb(f"SELECT * FROM {READ}", fmt="FORMAT parquet"),
        },
    ),
}


# --------------------------------------------------------------------------- data


def write_synthetic(path: Path, rows: int, seed: int = SEED) -> None:
    """A deterministic CSV with text, numbers, dates and quoted values."""
    rng = random.Random(seed)
    cities = [f"City {i:03d}" for i in range(500)]
    names = [f"Name {i:04d}" for i in range(5000)]
    comments = ["", "ok", 'said "fine", then left', "multi\nline", "a,b,c", "plain text"]
    with path.open("w", newline="", encoding="utf8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["id", "name", "city", "category", "amount", "qty", "date", "flag", "comment"]
        )
        for i in range(1, rows + 1):
            writer.writerow(
                [
                    i,
                    rng.choice(names),
                    rng.choice(cities),
                    f"cat_{rng.randrange(10)}",
                    f"{rng.uniform(0, 10000):.2f}",
                    rng.randrange(1, 100),
                    f"20{rng.randrange(20, 26)}-{rng.randrange(1, 13):02d}-{rng.randrange(1, 29):02d}",
                    rng.choice(("true", "false")),
                    rng.choice(comments),
                ]
            )


def prepare(directory: Path, rows: int, price_paid: str | None, download: bool) -> None:
    """Write the data files of :data:`DATASETS` into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    write_synthetic(directory / "synthetic.csv", rows)
    with (directory / "categories.csv").open("w", newline="", encoding="utf8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["category", "label"])
        writer.writerows([f"cat_{i}", f"Category {i}"] for i in range(10))
    if not price_paid and not download:
        return
    source = Path(price_paid) if price_paid else directory / "pp-2024.download.csv"
    if download and not price_paid:
        print(f"Downloading {PRICE_PAID_URL} (162.6 MB)", file=sys.stderr)
        urllib.request.urlretrieve(PRICE_PAID_URL, source)  # noqa: S310 - fixed public URL
    with (
        source.open("rb") as raw,
        (directory / "price-paid-2024.csv").open("wb") as target,
    ):
        target.write(PRICE_PAID_COLUMNS.encode() + b"\n")  # the file has no header row
        shutil.copyfileobj(raw, target, 1 << 20)
    with (directory / "property-types.csv").open("w", newline="", encoding="utf8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["property_type", "property_type_name"])
        writer.writerows(PROPERTY_TYPES.items())


# --------------------------------------------------------------------------- run


def command(task: str, tool: str, dataset: Dataset, directory: Path, out: Path) -> str | None:
    """The shell command of ``tool`` for ``task``, or ``None`` when the tool has none."""
    template = TASKS[task][2].get(tool)
    if template is None:
        return None
    values = {**asdict(dataset), "data": str(directory / dataset.file)}
    values["lookup"] = str(directory / dataset.lookup)
    values["out"] = str(out)
    values["out_dir"] = str(out.parent)
    return template.format(**values)


def check(kind: str, out: Path) -> int | None:
    """What the output says: a count, rows written, or ``None`` when not checked."""
    if kind == "none":
        return None
    if kind == "number":
        numbers = re.findall(r"\d+", out.read_text(encoding="utf8", errors="replace"))
        return int(numbers[-1]) if numbers else None
    if kind == "lines":
        with out.open("rb") as handle:
            return sum(1 for line in handle if line.strip())
    if kind == "parquet":
        import pyarrow.parquet as pq

        files = [out] if out.is_file() else sorted(out.parent.glob("*.parquet"))
        return sum(pq.read_metadata(path).num_rows for path in files)
    with out.open(newline="", encoding="utf8", errors="replace") as handle:
        return max(sum(1 for _ in csv.reader(handle)) - 1, 0)


def _peak_mb(usage: Any) -> float:
    # ru_maxrss is in bytes on macOS and in KiB on Linux.
    scale = 1 if sys.platform == "darwin" else 1024
    return round(usage.ru_maxrss * scale / 1_048_576, 1)


def _environment(paths: list[str]) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "AI_AGENT"}  # DuckDB's agent output
    env["UNDATUM_CACHE"] = "0"
    env["PATH"] = os.pathsep.join([*paths, env.get("PATH", "")])
    return env


def measure(shell: str, env: dict[str, str], timeout: float, out: Path) -> dict[str, Any]:
    """Run ``shell`` once in a fresh directory for ``out``: wall time and peak memory, or the error."""
    if out.parent.exists():
        shutil.rmtree(out.parent)
    out.parent.mkdir(parents=True)
    with tempfile.TemporaryFile() as err:
        start = time.perf_counter()
        proc = subprocess.Popen(
            ["bash", "-o", "pipefail", "-c", shell],
            stdout=subprocess.DEVNULL,
            stderr=err,
            env=env,
            cwd=out.parent,
            start_new_session=True,  # a timeout stops the whole pipeline
        )
        deadline = start + timeout
        while True:
            pid, status, usage = os.wait4(proc.pid, os.WNOHANG)
            if pid:
                break
            if time.perf_counter() > deadline:
                os.killpg(proc.pid, signal.SIGKILL)
                os.wait4(proc.pid, 0)
                return {"ok": False, "error": f"timeout after {timeout:.0f} s"}
            time.sleep(0.005)
        elapsed = time.perf_counter() - start
        code = os.waitstatus_to_exitcode(status)
        if code != 0:
            err.seek(0)
            lines = err.read().decode("utf8", "replace").strip().splitlines()
            return {"ok": False, "error": lines[-1][:200] if lines else f"exit {code}"}
    return {"ok": True, "seconds": elapsed, "rss_mb": _peak_mb(usage)}


def measure_task(
    jobs: dict[str, tuple[str, Path]],
    env: dict[str, str],
    repeat: int,
    timeout: float,
    slow: float,
) -> dict[str, dict[str, Any]]:
    """Run every tool's command of one task up to ``repeat`` times, taking turns.

    Each round runs every tool once, so a busy moment on the machine slows all tools rather
    than one of them; the fastest run counts. A command that takes longer than ``slow`` runs
    once, and a failed one is not repeated.
    """
    runs: dict[str, list[dict[str, Any]]] = {tool: [] for tool in jobs}
    failed: dict[str, dict[str, Any]] = {}
    for _ in range(repeat):
        for tool, (shell, out) in jobs.items():
            if tool in failed or (runs[tool] and runs[tool][-1]["seconds"] > slow):
                continue
            print(f"  {tool:8}", end=" ", file=sys.stderr, flush=True)
            result = measure(shell, env, timeout, out)
            print(result.get("error") or f"{result['seconds']:.3f}", file=sys.stderr)
            if result["ok"]:
                runs[tool].append(result)
            else:
                failed[tool] = result
    summary = dict(failed)
    for tool, done in runs.items():
        if tool not in failed:
            summary[tool] = {
                "ok": True,
                "seconds": round(min(r["seconds"] for r in done), 3),
                "runs": [round(r["seconds"], 3) for r in done],
                "rss_mb": max(r["rss_mb"] for r in done),
            }
    return {tool: summary[tool] for tool in jobs}


def versions(env: dict[str, str]) -> dict[str, str]:
    """The version line of every tool found on the ``PATH`` of ``env``."""
    found = {}
    for tool, (binary, probe) in TOOLS.items():
        if shutil.which(binary, path=env["PATH"]) is None:
            continue
        result = subprocess.run(
            ["bash", "-c", probe], capture_output=True, text=True, env=env, check=False
        )
        text = (result.stdout or result.stderr).strip().splitlines()
        found[tool] = text[0][:80] if text else "unknown"
    return found


def _machine() -> dict[str, Any]:
    info: dict[str, Any] = {"platform": platform.platform(), "cpus": os.cpu_count()}
    if sys.platform == "darwin":
        for key, name in (("cpu", "machdep.cpu.brand_string"), ("memory", "hw.memsize")):
            value = subprocess.run(
                ["sysctl", "-n", name], capture_output=True, text=True, check=False
            ).stdout.strip()
            info[key] = f"{int(value) / 2**30:.0f} GB" if key == "memory" and value else value
    else:
        info["cpu"] = platform.processor()
    return info


def run(
    directory: Path,
    paths: list[str],
    repeat: int,
    timeout: float,
    slow: float,
    tools: list[str] | None,
    tasks: list[str] | None,
) -> dict[str, Any]:
    """Run every task with every tool on every prepared dataset."""
    env = _environment(paths)
    found = versions(env)
    selected = [tool for tool in found if not tools or tool in tools]
    results = []
    datasets = {}
    with tempfile.TemporaryDirectory(prefix="undatum-compare-") as work:
        for name, dataset in DATASETS.items():
            data = directory / dataset.file
            if not data.exists():
                continue
            datasets[name] = {
                "title": dataset.title,
                "bytes": data.stat().st_size,
                "rows": check("rows", data),
            }
            for task, (ext, kind, _) in TASKS.items():
                if tasks and task not in tasks:
                    continue
                jobs = {}
                for tool in selected:
                    out = Path(work) / f"{name}-{task}-{tool}" / f"out.{ext}"
                    shell = command(task, tool, dataset, directory, out)
                    if shell is not None:
                        jobs[tool] = (shell, out)
                print(f"{name} {task}", file=sys.stderr, flush=True)
                for tool, result in measure_task(jobs, env, repeat, timeout, slow).items():
                    if result["ok"]:  # the output of the last run is still there
                        try:
                            result["check"] = check(kind, jobs[tool][1])
                        except (OSError, ValueError, csv.Error) as exc:
                            result["check"] = None
                            result["check_error"] = str(exc)[:200]
                    results.append({"dataset": name, "task": task, "tool": tool, **result})
    return {
        "created": dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "machine": _machine(),
        "tools": found,
        "repeat": repeat,
        "datasets": datasets,
        "results": results,
    }


# --------------------------------------------------------------------------- report


def _expected(rows: list[dict[str, Any]]) -> int | None:
    """The check value most tools agree on (undatum's on a tie)."""
    values = [row["check"] for row in rows if row.get("ok") and row.get("check") is not None]
    if not values:
        return None
    ranked = sorted(set(values), key=lambda v: (-values.count(v), v))
    undatum = next((r["check"] for r in rows if r["tool"] == "undatum" and r.get("ok")), None)
    if undatum in ranked and values.count(undatum) == values.count(ranked[0]):
        return undatum
    return ranked[0]


def _cell(row: dict[str, Any] | None, expected: int | None, notes: list[str]) -> str:
    if row is None:
        return "—"
    if not row.get("ok"):
        notes.append(f"{row['tool']} {row['task']} ({row['dataset']}): {row['error']}")
        return "failed" if "timeout" not in row["error"] else "timeout"
    text = f"{row['seconds']:.2f} s · {row['rss_mb']:.0f} MB"
    if expected is not None and row.get("check") not in (None, expected):
        notes.append(
            f"{row['tool']} {row['task']} ({row['dataset']}): {row['check']:,} rows, "
            f"others {expected:,}"
        )
        text += " ⚠"
    return text


def combine(documents: list[dict[str, Any]]) -> dict[str, Any]:
    """Several sessions of ``run`` as one: the fastest run of every cell, the largest peak memory.

    Other programs on the machine only make a run slower, so the fastest run over more sessions
    is the better estimate. A cell fails only when it failed in every session.
    """
    if len(documents) == 1:
        return documents[0]
    cells: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for document in documents:
        for row in document["results"]:
            cells.setdefault((row["dataset"], row["task"], row["tool"]), []).append(row)
    results = []
    for rows in cells.values():
        ok = [row for row in rows if row.get("ok")]
        if not ok:
            results.append(rows[-1])
            continue
        fastest = min(ok, key=lambda row: row["seconds"])
        runs = [seconds for row in ok for seconds in row.get("runs", [row["seconds"]])]
        results.append({**fastest, "runs": runs, "rss_mb": max(row["rss_mb"] for row in ok)})
    return {
        **documents[-1],
        "repeat": sum(document["repeat"] for document in documents),
        "sessions": len(documents),
        "results": results,
    }


def _version(text: str) -> str:
    """The version number in a tool's version line (qsv's also lists its features)."""
    match = re.search(r"\d+\.\d+(?:\.\d+)?", text)
    return match.group(0) if match else text


def markdown(results: dict[str, Any]) -> str:
    """Tables of seconds and peak memory per dataset, task and tool."""
    tools = list(results["tools"])
    sessions = results.get("sessions", 1)
    runs = f"fastest of up to {results['repeat']} runs" + (
        f" in {sessions} sessions" if sessions > 1 else ""
    )
    lines = [
        f"Measured {results['created'][:10]} on {results['machine'].get('cpu') or 'unknown'}, "
        f"{results['machine'].get('cpus')} cores, {results['machine'].get('memory', '?')} RAM "
        f"({results['machine']['platform']}); {runs}, peak resident memory.",
        "",
        "| Tool | Version |",
        "|---|---|",
        *(f"| {tool} | {_version(text)} |" for tool, text in results["tools"].items()),
        "",
    ]
    notes: list[str] = []
    for name, info in results["datasets"].items():
        lines += [
            f"### {info['title']}",
            "",
            f"{info['rows']:,} rows, {info['bytes'] / 1_048_576:.0f} MB.",
            "",
            "| Task | " + " | ".join(tools) + " |",
            "|---|" + "---|" * len(tools),
        ]
        for task in TASKS:
            rows = [r for r in results["results"] if r["dataset"] == name and r["task"] == task]
            if not rows:
                continue
            expected = _expected(rows)
            by_tool = {row["tool"]: row for row in rows}
            cells = [_cell(by_tool.get(tool), expected, notes) for tool in tools]
            lines.append(f"| {task} | " + " | ".join(cells) + " |")
        lines.append("")
    if notes:
        lines += ["Notes:", "", *(f"- {note}" for note in notes), ""]
    return "\n".join(lines)


def write_docs(page: Path, block: str) -> None:
    """Replace the generated block of ``page``."""
    text = page.read_text(encoding="utf8")
    start, end = text.index(BEGIN), text.index(END)
    page.write_text(text[: start + len(BEGIN)] + "\n" + block + "\n" + text[end:], encoding="utf8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("prepare", help="write the data files")
    p.add_argument("--dir", type=Path, required=True)
    p.add_argument("--rows", type=int, default=1_000_000, help="synthetic rows")
    p.add_argument("--price-paid", help="local copy of pp-2024.csv")
    p.add_argument("--download", action="store_true", help="download pp-2024.csv (162.6 MB)")
    r = sub.add_parser("run", help="measure every tool")
    r.add_argument("--dir", type=Path, required=True)
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--path", action="append", default=[], help="directory to search first")
    r.add_argument("--repeat", type=int, default=5)
    r.add_argument("--timeout", type=float, default=600, help="seconds per run")
    r.add_argument("--slow", type=float, default=60, help="run once when a run takes longer")
    r.add_argument("--tools", help="comma-separated subset")
    r.add_argument("--tasks", help="comma-separated subset")
    m = sub.add_parser("markdown", help="print (or write into a docs page) the tables")
    m.add_argument("results", type=Path, nargs="+", help="one or more results files, combined")
    m.add_argument("--docs", type=Path)
    args = parser.parse_args(argv)

    if args.action == "prepare":
        prepare(args.dir, args.rows, args.price_paid, args.download)
    elif args.action == "run":
        results = run(
            args.dir,
            [str(Path(p).expanduser()) for p in args.path],
            args.repeat,
            args.timeout,
            args.slow,
            args.tools.split(",") if args.tools else None,
            args.tasks.split(",") if args.tasks else None,
        )
        args.out.write_text(json.dumps(results, indent=2) + "\n", encoding="utf8")
    else:
        documents = [json.loads(path.read_text(encoding="utf8")) for path in args.results]
        block = markdown(combine(documents))
        if args.docs:
            write_docs(args.docs, block)
        else:
            print(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
