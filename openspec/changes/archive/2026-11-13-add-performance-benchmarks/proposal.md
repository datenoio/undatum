# Change: Performance and Memory Regression Gates

## Why
The only benchmark (`tests/benchmarks/test_schema_extraction.py`) is skipped, so the streaming and
low-memory claims are untested. Measured on a 500k-row (17 MB) CSV: `fill` 2.38 s / 507 MB,
`stats` 1.89 s / 356 MB, `count` 1.36 s / 237 MB (slower than `sort` at 0.87 s), `head --n 10`
0.78 s / 216 MB, while DuckDB alone sorts the same file in 0.13 s / 168 MB. Without measurements in
CI, regressions like #34 (swap usage during conversion) return unnoticed.

## What Changes
- Benchmark suite with generated reference datasets (100k and 1M rows CSV, JSONL, Parquet).
- Per-command budgets for wall time and peak RSS measured in a subprocess
  (`resource.getrusage(RUSAGE_CHILDREN)`), stored in `tests/benchmarks/budgets.toml`.
- Startup budget check (`--help`, `--version`) shared with `update-cli-startup-and-logging`.
- PR job runs the 100k tier and fails on > 20% regression against `master`; nightly job runs the
  1M tier and stores results (JSON artifact plus a history chart on the docs site).
- Investigate and fix `count` being slower than `sort` (use DuckDB `count(*)` or iterabledata
  totals where available).

## Impact
- Affected specs: `release-quality`
- Affected code: `tests/benchmarks/`, `.github/workflows/benchmarks.yml` (new), `undatum/cmds/counter.py`
