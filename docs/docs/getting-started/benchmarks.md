---
title: "Benchmarks"
description: "undatum compared with csvkit, Miller, qsv, xan and the DuckDB CLI"
---
# Benchmarks

The same ten tasks, run by undatum, [csvkit](https://csvkit.readthedocs.io/),
[Miller](https://miller.readthedocs.io/), [qsv](https://github.com/dathere/qsv),
[xan](https://github.com/medialab/xan) and the [DuckDB CLI](https://duckdb.org/docs/api/cli/overview)
on two CSV files. The numbers come from `scripts/compare_tools.py` in the repository, so anyone
can run them again (see [reproducing](#reproducing)).

These numbers do not crown a winner:
- Rust tools (qsv, xan) and the DuckDB CLI start in milliseconds. undatum and csvkit are Python
  programs that need 0.1–0.5 s to start, which dominates small files.
- undatum's reason to exist is breadth: 140+ formats, validation, data contracts, packaging, an
  SDK and an MCP server. On CSV it aims to be within reach of the fast tools, mostly by running
  DuckDB underneath.

## Tasks

| Task | What each tool computes |
|---|---|
| count | Number of records |
| select | Three columns to a CSV file |
| filter | Records with a number above a threshold, to a CSV file |
| sort | All records by a number, descending, to a CSV file |
| frequency | Counts of the values of one column |
| stats | Summary statistics of every column |
| dedup | The first record of every value of one column |
| join | Inner join with a small lookup table |
| to-jsonl | Conversion to JSON Lines |
| to-parquet | Conversion to Parquet |

The exact commands are in the `TASKS` table of `scripts/compare_tools.py`. Not every task is the
same amount of work in every tool:
- **csvkit** filters and counts values with `csvsql`, which loads the file into SQLite first. It
  has no dedup and no Parquet output.
- **Miller and xan** write no Parquet.
- **`stats` differs most.** The reports contain different measures (types, distinct values,
  lengths, quantiles, frequent values), so compare those times with care. undatum's report
  also lists every value and its count for each field with under 70% unique values
  (`--dictshare`), which on Price Paid means tens of thousands of street names.
- **Types:** undatum keeps CSV values as text (it types them for comparisons), and the DuckDB CLI
  and csvkit infer column types. JSON and Parquet outputs therefore differ in types, not in
  records.
- **Order:** `dedup` keeps the first record of each value in undatum, Miller and xan; qsv sorts its
  output and DuckDB keeps any one record per value.

After each run the script checks the output: the number of records counted or written. A tool
whose answer differs from the others is marked ⚠ and listed under the table.

## Results

Each cell is the wall time of the fastest run and the peak resident memory. Within a session the
tools take turns, one run each per round for up to five rounds, so a busy moment on the machine
slows them alike. Other programs only make a run slower, so the tables combine every session run
on this machine and keep the fastest run of each cell. A command that takes over a minute runs
once per session, and one that takes over three minutes is stopped (timeout). "—" means the tool
has no such command.

<!-- BEGIN GENERATED: comparison -->
Measured 2026-10-29 on Apple M4 Max, 14 cores, 36 GB RAM (macOS-26.5.1-arm64-arm-64bit); fastest of up to 14 runs in 4 sessions, peak resident memory.

| Tool | Version |
|---|---|
| undatum | 1.9.1 |
| csvkit | 2.2.0 |
| miller | 6.22.0 |
| qsv | 26.0.0 |
| xan | 0.61.0 |
| duckdb | 2.0.0 |

### Synthetic

1,000,000 rows, 67 MB.

| Task | undatum | csvkit | miller | qsv | xan | duckdb |
|---|---|---|---|---|---|---|
| count | 0.22 s · 143 MB | 1.96 s · 765 MB | 0.22 s · 174 MB | 0.05 s · 111 MB | 0.04 s · 12 MB | 0.06 s · 104 MB |
| select | 0.40 s · 145 MB | 1.25 s · 33 MB | 0.27 s · 536 MB | 0.10 s · 21 MB | 0.06 s · 12 MB | 0.10 s · 176 MB |
| filter | 0.77 s · 166 MB | timeout | 0.27 s · 518 MB | 0.12 s · 242 MB | 0.16 s · 13 MB | 0.15 s · 223 MB |
| sort | 0.40 s · 638 MB | 103.22 s · 1357 MB | 1.82 s · 1911 MB | 0.58 s · 321 MB | 1.44 s · 310 MB | 0.15 s · 472 MB |
| frequency | 0.51 s · 204 MB | 101.08 s · 2097 MB | 0.22 s · 132 MB | 0.11 s · 192 MB | 0.07 s · 13 MB | 0.07 s · 118 MB |
| stats | 2.52 s · 634 MB | 111.59 s · 1878 MB | 2.81 s · 1162 MB | 0.22 s · 29 MB | 0.52 s · 12 MB | 0.15 s · 137 MB |
| dedup | 1.79 s · 110 MB | — | 0.22 s · 271 MB | 0.26 s · 322 MB | 0.10 s · 12 MB | 0.11 s · 378 MB |
| join | 0.26 s · 211 MB | 99.03 s · 1437 MB | 0.47 s · 515 MB | 0.68 s · 21 MB | 0.36 s · 303 MB | 0.12 s · 166 MB |
| to-jsonl | 0.70 s · 155 MB | 102.34 s · 1329 MB | 0.99 s · 568 MB | 0.68 s · 115 MB | 0.43 s · 12 MB | 0.14 s · 552 MB |
| to-parquet | 2.27 s · 186 MB | — | — | 0.63 s · 286 MB | — | 0.73 s · 329 MB |

### UK Price Paid 2024

932,214 rows, 155 MB.

| Task | undatum | csvkit | miller | qsv | xan | duckdb |
|---|---|---|---|---|---|---|
| count | 0.24 s · 232 MB | 2.19 s · 795 MB | 0.73 s · 756 MB | 0.06 s · 196 MB | 0.12 s · 12 MB | 0.10 s · 193 MB |
| select | 0.53 s · 141 MB | 1.65 s · 33 MB | 0.75 s · 779 MB | 0.18 s · 21 MB | 0.15 s · 12 MB | 0.16 s · 276 MB |
| filter | 0.83 s · 163 MB | 147.75 s · 2537 MB | 0.73 s · 777 MB | 0.12 s · 432 MB | 0.22 s · 13 MB | 0.18 s · 300 MB |
| sort | 0.37 s · 1114 MB | 147.17 s · 1219 MB | 1.88 s · 3247 MB | 0.57 s · 366 MB | 1.04 s · 430 MB | 0.26 s · 1000 MB |
| frequency | 0.65 s · 202 MB | 149.65 s · 2537 MB | 0.74 s · 791 MB | 0.20 s · 200 MB | 0.16 s · 13 MB | 0.14 s · 216 MB |
| stats | 3.48 s · 979 MB | 153.83 s · 1670 MB | 4.38 s · 1581 MB | 0.32 s · 31 MB | 1.04 s · 12 MB | 0.21 s · 253 MB |
| dedup | 2.23 s · 112 MB | — | 0.75 s · 781 MB | 0.33 s · 366 MB | 0.22 s · 12 MB | 0.21 s · 730 MB |
| join | 0.33 s · 330 MB | 146.87 s · 1264 MB | 1.30 s · 843 MB | 0.76 s · 21 MB | 0.49 s · 424 MB | 0.22 s · 285 MB |
| to-jsonl | 1.16 s · 176 MB | 152.17 s · 1187 MB | 1.97 s · 921 MB | 1.77 s · 361 MB | 2.01 s · 13 MB | 0.50 s · 1091 MB |
| to-parquet | 0.82 s · 358 MB | — | — | 0.27 s · 689 MB | — | 0.28 s · 853 MB |

Notes:

- csvkit filter (synthetic): timeout after 180 s

<!-- END GENERATED: comparison -->

The machine was in everyday use, and its load changed the same command's time up to fivefold
within minutes. Treat differences under about 20% as noise.

## Datasets

- **Synthetic:** 1,000,000 rows of generated data (fixed seed) with text, numbers, dates and
  quoted values with commas, quotes and line breaks. It is joined with a 10-row category table.
- **[UK Price Paid 2024](https://www.gov.uk/government/statistical-data-sets/price-paid-data-downloads):**
  every residential property sale registered in England and Wales in 2024. HM Land Registry
  publishes it under the Open Government Licence v3.0. The file has no header row, so the script
  adds one. It is joined with a 5-row table of property types.

## Reproducing

```bash norun
# The tools: Homebrew shown; each project also ships binaries or packages
brew install miller qsv xan duckdb
pip install csvkit undatum

python scripts/compare_tools.py prepare --dir bench-compare --download
python scripts/compare_tools.py run --dir bench-compare --out results.json
python scripts/compare_tools.py markdown results.json

# More sessions, combined: the fastest run of every cell
python scripts/compare_tools.py run --dir bench-compare --out results-2.json
python scripts/compare_tools.py markdown results.json results-2.json
```

- `prepare --rows N` changes the size of the synthetic file.
- `run --tools undatum,qsv --tasks sort,join` measures a subset, and `--repeat`, `--timeout` and
  `--slow` set the runs.
- `--path DIR` puts a tool's directory first on `PATH` (for example a virtual environment with
  csvkit).
- On a laptop, keep it awake for the run (`caffeinate -i python scripts/compare_tools.py run ...`
  on macOS): runs measured while the machine sleeps or throttles idle programs are far slower.
- The script sets `UNDATUM_CACHE=0`, so undatum does not reuse [cached results](/commands/cache)
  between runs.

See also [Performance and large files](/getting-started/performance).
