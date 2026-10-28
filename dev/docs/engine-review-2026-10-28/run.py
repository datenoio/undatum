"""Time undatum, the DuckDB CLI and Polars on the same CSV file.

Usage: python run.py DATA.csv TAG [task,task...]   (TOOLS=undatum,duckdb,polars to filter)
Needs undatum and polars in this interpreter's environment and the DuckDB CLI on PATH
(or DUCKDB_CLI). Writes outputs to ./out and results to ./res_TAG.json; macOS /usr/bin/time.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time

SP = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
U = shutil.which("undatum") or "undatum"
DUCK = os.environ.get("DUCKDB_CLI", "duckdb")
F = sys.argv[1]  # data file
tag = sys.argv[2]
only = sys.argv[3].split(",") if len(sys.argv) > 3 else None
OUT = os.path.join(SP, "out")
os.makedirs(OUT, exist_ok=True)


def pl(code):
    return [PY, "-c", "import polars as pl\n" + code]


def dk(sql):
    return [DUCK, "-c", sql]


T = {
    "count": {
        "undatum": [U, "count", F],
        "undatum-py": [U, "count", F, "--engine", "python"],
        "duckdb": dk(f"SELECT count(*) FROM '{F}'"),
        "polars": pl(f"print(pl.scan_csv('{F}').select(pl.len()).collect())"),
    },
    "to_parquet": {
        "undatum": [U, "convert", F, f"{OUT}/u.parquet"],
        "undatum-py": [U, "convert", F, f"{OUT}/up.parquet", "--engine", "python"],
        "duckdb": dk(f"COPY (FROM '{F}') TO '{OUT}/d.parquet'"),
        "polars": pl(f"pl.scan_csv('{F}').sink_parquet('{OUT}/p.parquet')"),
    },
    "to_jsonl": {
        "undatum": [U, "convert", F, f"{OUT}/u.jsonl"],
        "undatum-py": [U, "convert", F, f"{OUT}/up.jsonl", "--engine", "python"],
        "duckdb": dk(f"COPY (FROM '{F}') TO '{OUT}/d.jsonl' (FORMAT json)"),
        "polars": pl(f"pl.scan_csv('{F}').sink_ndjson('{OUT}/p.jsonl')"),
    },
    "stats": {
        "undatum": [U, "stats", F],
        "undatum-py": [U, "stats", F, "--engine", "python"],
        "duckdb": dk(f"SUMMARIZE FROM '{F}'"),
        "polars": pl(f"print(pl.scan_csv('{F}').describe())"),
    },
    "frequency": {
        "undatum": [U, "frequency", F, "-f", "city"],
        "undatum-py": [U, "frequency", F, "-f", "city", "--engine", "python"],
        "duckdb": dk(f"SELECT city, count(*) c FROM '{F}' GROUP BY 1 ORDER BY 2 DESC"),
        "polars": pl(
            f"print(pl.scan_csv('{F}').group_by('city').len().sort('len', descending=True).collect())"
        ),
    },
    "uniq": {
        "undatum": [U, "uniq", F, "-f", "email"],
        "undatum-py": [U, "uniq", F, "-f", "email", "--engine", "python"],
        "duckdb": dk(f"COPY (SELECT DISTINCT email FROM '{F}') TO '{OUT}/d_uniq.csv'"),
        "polars": pl(f"pl.scan_csv('{F}').select('email').unique().sink_csv('{OUT}/p_uniq.csv')"),
    },
    "sort": {
        "undatum": [U, "sort", F, "--by", "amount", "-o", f"{OUT}/u_sorted.csv"],
        "undatum-py": [
            U,
            "sort",
            F,
            "--by",
            "amount",
            "-o",
            f"{OUT}/up_sorted.csv",
            "--engine",
            "python",
        ],
        "duckdb": dk(f"COPY (FROM '{F}' ORDER BY amount) TO '{OUT}/d_sorted.csv'"),
        "polars": pl(f"pl.scan_csv('{F}').sort('amount').sink_csv('{OUT}/p_sorted.csv')"),
    },
    "where": {
        "undatum": [
            U,
            "select",
            F,
            "--where",
            "amount > 9000 AND channel = 'online'",
            "-o",
            f"{OUT}/u_sel.csv",
        ],
        "undatum-py": [
            U,
            "select",
            F,
            "--where",
            "amount > 9000 AND channel = 'online'",
            "-o",
            f"{OUT}/up_sel.csv",
            "--engine",
            "python",
        ],
        "duckdb": dk(
            f"COPY (FROM '{F}' WHERE amount > 9000 AND channel = 'online') TO '{OUT}/d_sel.csv'"
        ),
        "polars": pl(
            f"pl.scan_csv('{F}').filter((pl.col('amount') > 9000) & (pl.col('channel') == 'online')).sink_csv('{OUT}/p_sel.csv')"
        ),
    },
    "dedup": {
        "undatum": [U, "dedup", F, "--key-fields", "email", "-o", f"{OUT}/u_dd.csv"],
        "undatum-py": [
            U,
            "dedup",
            F,
            "--key-fields",
            "email",
            "-o",
            f"{OUT}/up_dd.csv",
            "--engine",
            "python",
        ],
        "duckdb": dk(
            f"COPY (SELECT * FROM '{F}' QUALIFY row_number() OVER (PARTITION BY email ORDER BY id) = 1) TO '{OUT}/d_dd.csv'"
        ),
        "polars": pl(
            f"pl.scan_csv('{F}').unique(subset=['email'], keep='first', maintain_order=True).sink_csv('{OUT}/p_dd.csv')"
        ),
    },
}

res = {}
for task, tools in T.items():
    if only and task not in only:
        continue
    for tool, cmd in tools.items():
        if os.environ.get("TOOLS") and tool not in os.environ["TOOLS"].split(","):
            continue
        t0 = time.time()
        p = subprocess.run(
            ["/usr/bin/time", "-l", *cmd], check=False, capture_output=True, text=True, timeout=1800
        )
        dt = time.time() - t0
        m = re.search(r"(\d+)\s+maximum resident set size", p.stderr)
        rss = int(m.group(1)) / 1e6 if m else None
        ok = p.returncode == 0
        err = "" if ok else (p.stderr.strip().splitlines() or ["?"])[0][:120]
        res[f"{task}/{tool}"] = (round(dt, 2), round(rss) if rss else None, ok)
        print(
            f"{tag:6} {task:11} {tool:11} {dt:7.2f}s {rss and round(rss):6} MB {'OK' if ok else 'FAIL ' + err}",
            flush=True,
        )
with open(os.path.join(SP, f"res_{tag}.json"), "w") as fh:
    json.dump(res, fh, indent=1)
