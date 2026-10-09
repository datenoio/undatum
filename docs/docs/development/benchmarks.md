---
title: "Benchmarks"
description: "Wall time and peak memory of core commands, budgets, and the CI jobs that check them"
---
# Benchmarks

`scripts/benchmarks.py` measures the wall time and peak memory of core commands on generated
reference datasets. Each command runs in its own process: wall time is the median of three
runs, and peak memory is the largest resident set size the process reached.

## Running locally

```bash norun
make bench                       # 100k rows, checked against the budgets
python scripts/benchmarks.py generate --tier 1m --dir .bench-data/1m
python scripts/benchmarks.py run --tier 1m --data .bench-data/1m --out results.json
python scripts/benchmarks.py run --tier 100k --data .bench-data --only stats,sort --out r.json
python scripts/benchmarks.py check results.json
```

Tiers are `tiny` (2,000 rows, used by the harness tests), `100k` and `1m`. Each tier has a
CSV, a JSON Lines and a Parquet file with the same rows: numbers, dates, a quoted text field,
an MD5 code and free text. The values come from the row number, so every run writes the
same files.

To compare two versions on one machine, pass one interpreter per version. The commands are
measured in turns, so a busy machine affects both sides alike:

```bash norun
python scripts/benchmarks.py run --tier 100k --data .bench-data \
  --python base=../undatum-master/.venv/bin/python --python head=.venv/bin/python --out pr.json
python scripts/benchmarks.py compare pr.json --base base --head head
```

## Budgets

`tests/benchmarks/budgets.toml` sets a time and a memory budget for each command and tier.
Time budgets are about three times the measured time, which leaves room for slower CI
runners. Memory budgets are 1.3 × the measured peak + 20 MB, so a command that starts
holding a 100k-row input in memory goes over. `faster` lists pairs whose order must hold;
for example, `count` must stay faster than `sort`.

When a command gets faster, lower its budget. Raise a budget only with the reason in the
commit message.

## CI

| Job | When | What fails it |
|-----|------|---------------|
| `Benchmarks / 100k rows against the base branch` | pull requests that touch `undatum/`, dependencies or the harness | a command over 20% slower or larger than on the base branch (ignoring changes under 0.1 s and 15 MB), a command over its budget, or a command that fails |
| `Benchmarks / 1M rows (nightly history)` | every night on `master`, and on demand | a command over its 1M-row budget |
| `CI / memory-budget` | every push and pull request | a row command over 300 MB on 1M rows, or growing by more than 20% (and 40 MB) from 250k to 1M rows |

The pull-request job writes a comparison table to the run summary. The nightly job uploads
its results (`benchmarks-nightly-*`, kept for 90 days) and appends them to the
`benchmark-history` branch. The documentation site redraws this chart after each nightly run:

![Nightly benchmark history](/img/benchmark-history.svg)

## Findings from the first measurements (2026-10)

Measured on macOS arm64 with Python 3.13:

| Command | Before | After | Change |
|---------|--------|-------|--------|
| `stats` | 15.5 s (100k rows) | 2.5 s (100k rows) | date detection caches values, skips values without digits, and stops early on columns that are not dates |
| `rename`, `fill` | 3.0 s, 165 MB (100k rows) | 0.25 s, 86 MB (100k rows) | the output format of `.csv`, `.json`, `.jsonl` and `.parquet` files is known from the name; iterabledata is no longer imported for it |
| `count` | 0.53 s (500k rows) | 0.19 s (500k rows) | uses the shared DuckDB reader; ORC, Arrow and DBF use the row count stored in the file |
| `sort` | fell back to Python for paths with `'` and fields with spaces | stays in DuckDB | quoted identifiers and the shared reader |

Open items: `sort` peaks at about 900 MB on 1M rows (DuckDB sorts with every core; one thread
needs 455 MB). Converting CSV to Parquet peaks at about 800 MB. Converting Parquet to JSON
Lines takes 5.5 s through the Python writer.
