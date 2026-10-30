## Context

The numbers come from `dev/docs/ENGINE_AND_COMPETITOR_REVIEW_2026-10-28.md`, section 4, and its
scripts in `dev/docs/engine-review-2026-10-28/`. Setup: macOS arm64 with 14 cores, a 2M-row CSV
of 275 MB, undatum 1.9.1, DuckDB 1.5 and Polars 2.1. Times include process start-up.

| Operation | undatum (auto) | DuckDB CLI | Polars 2.1 |
|---|---|---|---|
| CSV → Parquet | 1.58 s | 0.29 s | 0.37 s |
| CSV → JSONL (Python path) | 7.45 s | 0.64 s | 0.65 s |
| frequency | 1.14 s | 0.10 s | 0.26 s |
| `--where` → CSV | 2.19 s | 0.13 s | 0.29 s |
| dedup (Python path) | 9.38 s | 0.22 s | 0.32 s |

Where the undatum time goes:

- **Imports.** On DuckDB paths undatum still imports iterabledata (0.32 s) and pyarrow (0.14 s).
  Commands that import pandas add another 0.70 s.
- **Result conversion.** DuckDB results become dicts in `write_query` (`fetchmany` → `dict(zip)`
  → `normalize_for_json`, twice). `uniq` and `frequency` read their results with `fetchall`.
- **Threads.** Aggregations run on the global connection, or on one thread in the ops runner.
- **Duplicated reads.** `selector`, `sampler`, `joiner` and `converter` each build their own
  `read_csv_auto(...)` expression, and some of them do not escape the path.

## Goals / Non-Goals

**Goals:**
- DuckDB executes every SQL-expressible operation by default.
- Arrow is the interchange between iterabledata, DuckDB and the SDK.
- One type-inference rule set.
- `stats` cost no longer scales with the number of fields.
- Records stay identical to the Python engine.

**Non-Goals:**
- Replacing iterabledata's readers and writers.
- A second engine (Polars, DataFusion, chDB).
- Changing CLI options or JSON layouts.
- Distributed execution.

## Decisions

### Keep DuckDB; no Polars engine
Polars 2.1 was compared with DuckDB on the same machine (review sections 4 and 5.2).

- **Speed.** Polars is faster only on `sort`, at 0.61 s against 0.65 s. On the other eight
  operations it is equal or slower. Independent 2026 comparisons agree within 1–3× in either
  direction, and DuckDB alone completes under a ~6 GB memory cap.
- **Weight.** `polars-runtime-32` is a 48–54 MB wheel and 153 MB installed; DuckDB takes 44 MB.
- **Messy CSV defaults.** Polars infers the schema from 100 rows and fails on a later type
  change. Its `ignore_errors` drops rows without a report. It reads no non-UTF-8 encodings.
- **Churn.** Polars ships a major release about every six months (2.0 in October 2026), and its
  streaming joins and group-bys drop row order unless `maintain_order=True`.
- **Duplication.** A second SQL dialect would repeat `--where`/`--add` semantics, type inference
  and text preservation.

Polars stays an optional extra for SDK interchange through Arrow.

### Arrow is the interchange
- **Formats DuckDB does not read.** iterabledata produces a `pyarrow.RecordBatchReader`, and
  DuckDB scans it without a copy. Operations with a SQL form run on it, so one implementation
  serves every format that has an Arrow adapter.
- **Output.** `COPY` writes CSV and Parquet, and JSON Lines when the text equals the Python
  writer's. Other formats and stdout take Arrow batches through the existing iterabledata
  writers.
- **SDK.** `to_arrow()` returns a `pyarrow.Table` or `RecordBatchReader`; `to_polars()` and
  `to_pandas()` wrap it.

### Text and type semantics
- **CSV stays text.** CSV is read with `all_varchar`. `--where`/`--add` keep their typed shadow
  columns (`ops/expr.py`), so output text is unchanged.
- **NULL against empty string.** DuckDB reads empty CSV fields as NULL, and the Python reader
  gives `''`. Writers must produce the same text for both. JSON output from CSV input is part of
  the contract suite.
- **Temporal values.** Temporal columns are formatted as Python's `isoformat()` before `COPY`,
  so the `_TEMPORAL` exclusion in `ops/runner.py` can go.
- **Type inference.** A field's type is the narrowest DuckDB type that `TRY_CAST` succeeds on for
  ≥95% of non-empty sampled values. That rule already lives in `ops/expr.py`; it moves to a shared
  module.
- **Dates.** Values of type DATE or TIMESTAMP (by `TRY_CAST` or the CSV sniffer) are dates.
  qddate runs only on leftover text that `could_be_date()` admits, at most 20 values per field.

### Workload classes
- **ROW and WINDOW operations** (rename, fill, head, ...) keep `threads=1` and 256 MB. Order is
  preserved and the memory budget holds.
- **Aggregations and sorts** (stats, frequency, uniq, count, sort, join) use all cores and
  DuckDB's default memory limit.
- **Operations that hold every record** (`sql_holds_all_rows`: dedup, reverse) use DuckDB only
  with `--engine duckdb`. Under the 256 MiB runner limit, DuckDB 1.5 failed the window/sort these
  need with an out-of-memory error.

### `stats` query plan
1. **One aggregate query over all columns:** `count`, `count(col)`, `min`/`max`,
   `approx_count_distinct`, `min/avg/max(length(col))`, and `TRY_CAST` shares for type candidates.
2. **One grouped query for dictionaries:** `GROUP BY GROUPING SETS ((c1), (c2), ...)` over the
   columns whose distinct estimate is under `dictshare`, limited to the top-k per column.

## Risks / Trade-offs
- **Semantic drift between engines.** The contract suite (`tests/test_ops_contract.py`) is
  extended to every operation, every native format pair and Arrow-bridged inputs, including
  output from CSV to JSON.
- **Memory of aggregations on all cores.** These run outside the streaming budget, as they do
  today. The benchmark budgets record their peak RSS.
- **Arrow adapters missing in iterabledata.** Formats without one stay on the Python path.
  iterabledata gains adapters format by format.
- **DuckDB versions.** This change needs DuckDB 2.0's relation-to-Arrow API, so it lands after
  `update-python-311-duckdb-2`.

## Migration Plan
1. Connection factory with workload classes. Move `stats`, `count`, `analyze`, `schema`,
   `quality`, `drift` and `Where` onto it.
2. `convert` through `COPY`, with the contract suite extended to conversions.
3. Shared type-inference module, then `stats` single-pass.
4. Output without dicts (`COPY` / Arrow batches), then remove the `_TEMPORAL` exclusion.
5. Arrow bridge for non-native formats, then remove the per-command DuckDB paths.
6. SDK SQL compilation for the remaining methods, and `to_arrow()`.

Each step ships on its own, with the benchmark comparison against the base branch.

## Open Questions
- **Reading Excel:** use the DuckDB `excel` extension (an extension download, first-row
  inference, no `.xls`) or `fastexcel`/calamine (3–4 MB; reads xls/xlsx/xlsb/ods into Arrow)?
- **Streaming to stdout:** `COPY ... TO '/dev/stdout'` is fastest but unavailable on Windows.
  Arrow batches to the stdout writer may be enough.
