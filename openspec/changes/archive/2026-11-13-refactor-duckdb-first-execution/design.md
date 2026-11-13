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
- **Formats DuckDB does not read.** iterabledata has no Arrow reader API, so undatum reads the
  formats pyarrow reads itself (`RowSource.arrow_reader()`: ORC stripe by stripe, Arrow
  IPC/Feather files and streams memory-mapped; decided with the maintainer) and DuckDB scans the
  `pyarrow.RecordBatchReader` without a copy. `pyarrow.dataset` is not used: importing it imports
  pandas (2.5 s). A reader is read once, so each `RowSource.duckdb_relation()` serves one query;
  a query that reads its input twice fails and falls back to Python (partitioned `convert` keeps
  native readers for this reason). DuckDB cannot select a reader's columns, so `uniq` and
  `frequency` ask for their fields only. Excel stays on the Python reader: openpyxl takes 4.4 of
  the 4.6 s of `frequency` on 100k rows, and turning its rows into Arrow adds 0.65 s (decision
  1.2). Measured on 1M ORC rows against `--engine python`: `frequency` 1.8 s to 0.8 s,
  `uniq` 3.1 s to 1.9 s, `sort` to CSV 8.3 s to 1.0 s, `rename` to Parquet 4.6 s to 0.6 s,
  `convert` to Parquet 4.2 s to 1.0 s; peak memory grows with the stripe size (400–470 MB for row
  commands instead of 130–300 MB).
- **Output.** `COPY` writes CSV and Parquet, and JSON Lines when the text equals the Python
  writer's. Other formats and stdout take DuckDB's result batches through the existing
  iterabledata writers. Arrow batches were measured for this (1M rows, 8 columns): `fetchmany`
  into dicts 0.78 s, Arrow `to_pylist` 0.88 s, Arrow columns zipped 0.67 s, and Arrow changes the
  Python values of HUGEINT, UUID, INTERVAL and MAP, so record writers keep `fetchmany`. The cost
  was the JSON conversion of every record, done twice (1.05 s per pass per 1M records); it is now
  done once, with a fast path for records of scalars (0.17 s).
- **CSV headers.** DuckDB's sniffer decides the header itself: it took a later line for the
  header when a row had more values than the first line, named a numeric header `column0`, ...,
  and trimmed names. Every DuckDB read of CSV text names the columns from the first line as the
  csv module reads it (`read_csv(..., header=true, auto_detect=false, columns={...})`, all
  `VARCHAR`), which also skips sniffing (1M rows: same time). DuckDB rejects empty names and
  names that differ only by case, so such files keep the Python reader. `schema`, `analyze`,
  `stats` and `doc` read CSV structure the same way and type it with the shared rules.
- **SDK.** `Dataset._sql()` composes the plan with `compose_sql` over
  `RowSource.duckdb_relation()` (native readers and the Arrow bridge) for `write`, `count`,
  `head`, `uniq`, `frequency`, `schema` and the exports. Methods that return records must give
  the Python engine's values, so the relation is adjusted or refused: CSV is wrapped in
  `COALESCE(column, '')` and used only when DuckDB's column names equal the header the Python
  reader takes (a byte-order mark, which DuckDB drops, and headers DuckDB cannot name fall back);
  JSON is refused, because `read_json_auto` types strings as dates and joins integers and
  floats; Parquet, ORC and Arrow columns must have types whose Python values are the same
  (checked type by type: nanosecond and zoned timestamps, maps, intervals, UUIDs and Parquet
  durations are not). `count` needs only the same rows, so JSON counts in DuckDB, and without
  steps it is `undatum count`. `uniq` and `frequency` keep first-seen order with
  `row_number() OVER ()` on one thread. `to_arrow()` returns a `pyarrow.Table` (or tables of
  `chunksize` rows, re-batched to that size); other plans convert their records in batches,
  and `to_pandas()`/`to_polars()` build a batch Arrow cannot type (a field mixing value types)
  from its records. 1M CSV rows: `count` 10.2 s to 0.2 s, `uniq`/`frequency` 8 s to 0.2 s,
  `filter(query=...).count()` 55 s to 0.07 s, `to_pandas()` 20.9 s to 0.9 s.

### Text and type semantics
- **CSV stays text.** CSV is read with `all_varchar`. `--where`/`--add` keep their typed shadow
  columns (`ops/expr.py`), so output text is unchanged.
- **NULL against empty string.** DuckDB reads empty CSV fields as NULL, and the Python reader
  gives `''`. Writers must produce the same text for both. JSON output from CSV input is part of
  the contract suite.
- **Temporal values.** The `_TEMPORAL` exclusion in `ops/runner.py` is replaced by one per-type
  rule shared with `convert` (`duckdb_copy_keeps_values`), checked type by type against the
  Python writer: dates use `COPY` in CSV and Parquet, timestamps and times only in Parquet (in
  CSV DuckDB shortens fractional seconds: `10:30:00.5` for `10:30:00.500000`). Parquet also keeps
  UUIDs, intervals and times with a zone on the Python writer. CSV `COPY` writes CRLF line ends,
  as the Python csv writer does. JSON Lines from `convert` keep times through DuckDB, since the
  iterabledata JSON writers up to 1.0.23 write them as `null` (fixed in iterabledata#27); once
  undatum requires that release, times can follow the CSV rule or be formatted in SQL.
- **Type inference** (`undatum/common/field_types.py`, decided with the maintainer). Text values
  get the first of integer, number, boolean, date and datetime that ≥95% of the non-empty values of
  a 10,000-record sample convert to, in every command (schema-drift used 100%); typed inputs keep
  their types, so a JSON string `"2005"` stays a string (schema exports must match the data).
  `stats` reports the new `bool` and `datetime` names; objects and arrays stay `str` there.
- **Dates.** ISO dates and day-first dates (`%d.%m.%Y`, `%d/%m/%Y`, `%d-%m-%Y`, `%Y/%m/%d`),
  checked in SQL so that `quality` measures conformance with the same condition. qddate no longer
  decides a type: dates in words ("12 сентября 2018") are strings, as everywhere but `stats` before.
- **`--where`** keeps the types `TRY_CAST` reads (ISO dates only), since expressions cast to them.
- **`db load`** keeps its own rule for now: a created column must hold every value, which a 95%
  threshold cannot promise.

### Workload classes
- **ROW and WINDOW operations** (rename, fill, head, ...) keep `threads=1` and 256 MB. Order is
  preserved and the memory budget holds.
- **Aggregations and sorts** (stats, frequency, uniq, count, sort, join) use all cores and
  DuckDB's default memory limit.
- **Operations that hold every record** (`sql_holds_all_rows`: dedup, reverse) use DuckDB only
  with `--engine duckdb`. Under the 256 MiB runner limit, DuckDB 1.5 failed the window/sort these
  need with an out-of-memory error. Later (DuckDB 2.0) dedup became one `GROUP BY` that holds a
  record per key, and `auto` runs it when `approx_count_distinct` estimates at most
  `memory_keys` keys (`Operation.sql_fits`).

### `stats` query plan
1. **One aggregate query over all columns:** `count(*)`, `count(col)`, `approx_count_distinct`
   (what `SUMMARIZE` reported), `min/max/avg(length(col))`, and `min/max/avg/median/stddev` of the
   numeric columns.
2. **Dictionaries:** `GROUP BY GROUPING SETS ((c1), ..., (c4))` over the columns whose distinct
   share is under `dictshare`, four columns per scan. The dictionaries also give these columns'
   exact distinct counts.
3. **Exact distinct counts of the other columns:** `COUNT(DISTINCT ...)`, packed into scans of at
   most 2,000,000 estimated distinct values.

Measured, not assumed: one query with `COUNT(DISTINCT)` over every column was fastest but held
every column's values at once (big.csv, 2M rows: 1.99 GB against 1.15 GB per field). DuckDB does
not spill ungrouped distinct aggregates, so a memory limit made it fail rather than spill, and a
`GROUPING SETS` over 61 columns failed even with 1 GB. Four dictionary columns per scan gave the
best balance (2M rows: 5.7 s / 1.29 GB; 100k x 61 columns: 4.0 s / 830 MB against 10.2 s /
690 MB per field).

## Risks / Trade-offs
- **Semantic drift between engines.** The contract suite (`tests/test_ops_contract.py`) is
  extended to every operation, every native format pair and Arrow-bridged inputs, including
  output from CSV to JSON.
- **Memory of aggregations on all cores.** These run outside the streaming budget, as they do
  today. The benchmark budgets record their peak RSS.
- **Arrow adapters missing in iterabledata.** undatum reads ORC and Arrow/Feather with pyarrow
  itself; other formats stay on the Python path until iterabledata gains Arrow readers, which can
  then replace `RowSource.arrow_reader()`.
- **DuckDB versions.** This change needs DuckDB 2.0's relation-to-Arrow API, so it lands after
  `update-python-311-duckdb-2`.

## Migration Plan
1. Connection factory with workload classes. Move `stats`, `count`, `analyze`, `schema`,
   `quality`, `drift` and `Where` onto it.
2. `convert` through `COPY`, with the contract suite extended to conversions.
3. `stats` in a few grouped scans, then the shared type-inference module.
4. Output without dicts (`COPY` / Arrow batches), then remove the `_TEMPORAL` exclusion.
5. Arrow bridge for non-native formats, then remove the per-command DuckDB paths.
6. SDK SQL compilation for the remaining methods, and `to_arrow()`.

Each step ships on its own, with the benchmark comparison against the base branch.

## Open Questions
- **Reading Excel (left for a later change):** the DuckDB `excel` extension (an extension
  download, first-row inference, no `.xls`) or `fastexcel`/calamine (3–4 MB; reads
  xls/xlsx/xlsb/ods into Arrow)? Either replaces openpyxl, which is most of the time spent.
- **Streaming to stdout (resolved):** DuckDB results reach stdout in batches through the Python
  writers, so the text is the Python engine's on every platform; `COPY ... TO '/dev/stdout'` is
  not used.
