"""Read a messy CSV with undatum, DuckDB and Polars defaults. Usage: python probe.py FILE.csv"""

import shutil
import subprocess
import sys

path = sys.argv[1]
UNDATUM = shutil.which("undatum") or "undatum"


def first_line(text: str) -> str:
    return (text.strip().splitlines() or [""])[0][:110]


def with_undatum() -> str:
    head = subprocess.run(
        [UNDATUM, "head", path, "-n", "2", "-O", "jsonl"],
        check=False,
        capture_output=True,
        text=True,
    )
    count = subprocess.run([UNDATUM, "count", path], check=False, capture_output=True, text=True)
    return (
        f"{first_line(head.stdout) or first_line(head.stderr)} (exit {head.returncode})"
        f" | count={first_line(count.stdout) or first_line(count.stderr)}"
    )


def with_duckdb() -> str:
    import duckdb

    first = duckdb.sql(f"SELECT * FROM '{path}' LIMIT 1").fetchall()
    total = duckdb.sql(f"SELECT count(*) FROM '{path}'").fetchone()
    return f"{first[0]} | count={total[0] if total else None}"


def with_polars() -> str:
    import polars as pl

    frame = pl.read_csv(path)
    return f"{frame.row(0)} | count={frame.height}"


print(path)
for name, reader in (("undatum", with_undatum), ("duckdb", with_duckdb), ("polars", with_polars)):
    try:
        print(f"  {name:8} {reader()}")
    except Exception as exc:  # noqa: BLE001 - report every reader's failure
        print(f"  {name:8} ERROR {type(exc).__name__}: {first_line(str(exc))}")
