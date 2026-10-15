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
Time budgets are about three times the time measured on a Mac (arm64) and, for 100k rows, at
least 1.4 × the time on the GitHub `ubuntu-latest` runner, which is 3–5 times slower for
commands that import iterabledata. Memory budgets are 1.3 × the measured peak + 20 MB, so a command that starts
holding a 100k-row input in memory goes over. `faster` lists pairs whose order must hold;
for example, `count` must stay faster than `sort`.

When a command gets faster, lower its budget. Raise a budget only with the reason in the
commit message.

## CI

| Job | When | What fails it |
|-----|------|---------------|
| `Benchmarks / 100k rows against the base branch` | pull requests that touch `undatum/`, dependencies or the harness | a command over 20% slower or larger than on the base branch (ignoring changes under 0.1 s and 15 MB), a command over its budget, or a command that fails |
| `Benchmarks / 1M rows (history)` | on demand only (Actions → Benchmarks → Run workflow); the nightly schedule is off | a command over its 1M-row budget |
| `CI / memory-budget` | every push and pull request | a row command over 300 MB on 1M rows, or growing by more than 20% (and 40 MB) from 250k to 1M rows |

The pull-request job writes a comparison table to the run summary. The 1M-row job uploads
its results (`benchmarks-nightly-*`, kept for 90 days) and appends them to the
`benchmark-history` branch. The documentation site redraws this chart after each run:

![Benchmark history](/img/benchmark-history.svg)

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

## Verified repack benchmarks

`scripts/benchmark_repack.py` generates low/high-cardinality CSV, JSONL, gzip/zstd
streams, tiny/empty gzip and typed Parquet/ORC/Avro fixtures. It records physical
sizes, encode/verify times, cold process-tree RSS, candidate scratch and read-back
or downstream scan time. Independent preservation checks apply to every implementation;
failed or lossy outputs are retained as failures rather than reported as compression wins.

```bash norun
pip install "undatum[dev,repack,compression]"
# Three repeats, rotating implementations/profiles to reduce ordering effects
python scripts/benchmark_repack.py --size-mib 1 --repeat 3 \
  --output repack.json --budgets tests/benchmarks/repack_budgets.json
# Compare the previous repacker and an installed local filerepack checkout
python scripts/benchmark_repack.py --baseline-ref HEAD --repeat 3 \
  --filerepack-root ../filerepack --filerepack-python ../filerepack/venv/bin/python \
  --output comparison.json
# Larger corpus and a focused Parquet layout experiment
python scripts/benchmark_repack.py --size-mib 16 --profiles max --output large.json
python scripts/benchmark_repack.py --size-mib 16 --profiles max --only typed.parquet \
  --batch-size 8192 --row-group-size 131072 --output layout.json
```

The checked-in JSON budgets apply to the **1 MiB** corpus and its current profiles.
They gate preservation, time, RSS, output size and scratch. To recalibrate on a chosen
runner, use `--calibrate PATH`, inspect the measurements, then review the budget diff.
The current local margins are max(3 × median time, median + 1 s), 1.3 × RSS + 20 MiB,
3% + 16 bytes for output and 20% + 4 KiB for scratch. These are local regression
budgets; Linux CI calibration and automatic CI wiring remain separate work.

Evidence is saved in `openspec/changes/archive/2026-10-15-improve-repack-preservation/benchmarks*.json`.
Each report records Python/library versions, Git revisions and implementation hashes;
the filerepack comparison uses its local modified checkout, not a released package.
The new command is measured through the CLI, while both baselines use their APIs in
cold subprocesses, so end-to-end time includes different startup costs. On the shared
workstation timing varied substantially; no general speedup is inferred from these runs.

The 2026-10-13 runs used Python 3.10.20, iterabledata 1.0.23, PyArrow 25.0.1 and
pyorc 0.11.0 on macOS arm64. All 27 profile/case combinations and all larger-corpus
candidates passed independent preservation. Representative max-profile physical sizes:

| Case | Input bytes | Verified candidate bytes | Finding |
|------|-------------|--------------------------|---------|
| Tiny gzip | 28 | 28 | Previous repacker wrote 57 bytes; no-growth now retains the original by default |
| Empty gzip | 20 | 20 | Previous repacker wrote 50 bytes |
| Typed Parquet | 54,023 | 25,875 | Same size as the verified comparable filerepack candidate at zstd level 19 |
| Typed ORC | 11,055 | 8,561 | Original types/rows retained; previous repacker's 123-byte output loses rows |
| Typed Avro | 508,268 | 32,226 | Encoded records/schema/metadata retained; previous smaller output changes types |
| High-cardinality zstd | 479,865 | 494,874 | More effort can grow output; normal no-growth mode rejects this candidate |

Trials deliberately use `--allow-grow` to expose each profile's actual candidate. The
local filerepack ORC adapter refuses these fixtures because it passes a RecordBatch to
an ORC writer requiring a Table; its failure time is not a valid successful-repack result.
Gzip comparison uses level 9 and zstd comparison level 19, one codec thread, relaxed
filerepack native budgets and the same Python/data libraries.

On the 16 MiB corpus, gzip/Avro RSS stayed around 56–57 MiB; zstd max used about
155 MiB, showing native codec memory beyond the transfer buffer. Parquet with the default
65,536-row batch/group used about 150 MiB. Changing to 8,192-row batches and a
131,072-row group raised it to about 160 MiB, increased output from 397,504 to
403,786 bytes and did not improve time. Keep the default layout; tune explicit settings
for a particular workload and measure downstream read-back as well as compression.
