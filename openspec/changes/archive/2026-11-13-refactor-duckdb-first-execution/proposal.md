# Change: DuckDB-First, Arrow-Native Execution

## Why
The 2026-10-28 engine review (`dev/docs/ENGINE_AND_COMPETITOR_REVIEW_2026-10-28.md`)
benchmarked undatum 1.9.1 against the DuckDB CLI and Polars 2.1 on 2M CSV rows:

- **Commands that already run in DuckDB are 2–17× slower than the DuckDB CLI.** The causes are
  conversion of results to Python dicts (`fetchall`/`fetchmany`), one-thread defaults, and about
  0.6 s of imports.
- **Commands that do not run in DuckDB are slower still:** `convert` CSV→JSONL by 12×, `dedup`
  by 43×.
- **`stats` is wasteful:** 4 queries per field, plus a Python type-sampling pass over 10k rows.
- **Type inference is implemented seven times** with different rules, so `schema`, `stats`,
  `quality` and `schema-drift` can disagree about the same column.
- **Inputs DuckDB cannot read natively never use it at all.** These are XLSX, Avro, ORC, XML and
  the rest of iterabledata's formats.

Polars 2.1, DataFusion, chDB, Ibis and Daft were evaluated as alternative or additional engines.
None is faster than DuckDB for these operations. Each adds weight (the Polars runtime is 153 MB
installed, against 44 MB for DuckDB) and its own SQL dialect, and Polars is strict on messy CSV
(see `design.md`). DuckDB is already the SQL engine behind `--where`/`--add`. The gap is how
undatum uses it, not which engine it uses.

## What Changes
- **Conversion through DuckDB.** `convert` with `--engine auto` uses DuckDB `COPY` for pairs it
  reads and writes natively (CSV/TSV, JSON, JSON Lines, Parquet; plain, gzip or zstd). CSV text is
  preserved (`all_varchar`), checked by contract tests against the Python engine.
- **One DuckDB connection factory with workload settings:**
  - `create_duckdb_connection` is used everywhere, including `stats`, `count`, `analyze`,
    `schema`, `quality`, `schema-drift`, `--where` and the `selector`/`sorter`/`sampler`/`joiner`
    paths;
  - row-wise transforms keep one thread and 256 MB;
  - aggregations and sorts use all cores and DuckDB's own memory limit unless
    `--duckdb-threads`/`--duckdb-memory` say otherwise;
  - the temp directory is honoured everywhere.
- **`stats` in at most two scans**, whatever the number of fields:
  - one aggregate query over all columns (counts, nulls, min/max, `approx_count_distinct`,
    lengths, `SUMMARIZE`);
  - one grouped query for dictionary candidates;
  - no per-field queries, and no `fetchall` of high-cardinality columns.
- **One type-inference module, based on DuckDB:**
  - it uses `TRY_CAST` shares over a sample, with qddate only for leftover date-shaped text;
  - it is used by `schema`, `stats`, `quality`, `schema-drift` and `db load`, replacing the seven
    current implementations.
- **Arrow bridge:**
  - sources that iterabledata can stream as Arrow record batches are registered in DuckDB;
  - SQL-expressible operations then run in DuckDB for XLSX, Avro, ORC and other formats too, with
    results equal to the Python engine.
- **No dict round-trip on DuckDB paths.** Output uses `COPY` (CSV, Parquet, JSON Lines when the
  text is equal), or Arrow batches handed to the existing writers.
- **One SQL path per operation.** The per-command DuckDB read builders and duplicate
  implementations are removed in favour of `RowSource.duckdb_from()` and the `ops` registry:
  - `selector.py` (`uniq`, `frequency`, `select`);
  - `sorter.py`, `sampler.py`, `joiner.py`;
  - `converter.py`;
  - `Dataset._sql_query` (duplicates `ops.runner.compose_sql`).
- **SDK:**
  - `count`, `head`, `uniq`, `frequency` and `schema` compile to SQL;
  - `to_arrow()` is new, and `to_polars()`/`to_pandas()` go through Arrow instead of a list of
    dicts.
- **Kept as is:**
  - operations whose SQL form holds every record (`Operation.sql_holds_all_rows`: `dedup`,
    `reverse`) still need `--engine duckdb`, so the default stays within the bounded-memory
    budget of `refactor-streaming-operations-core`;
  - iterabledata stays the reader and writer for every format DuckDB does not handle natively;
  - `--engine python` stays available.

## Impact
- Affected specs: `data-processing`, `sdk`
- Affected code:
  - `undatum/ops/` (runner, operations);
  - `undatum/io/`;
  - `undatum/common/{duckdb_config,command_utils,engine_selector,writer,schema_utils}.py`;
  - `undatum/cmds/{converter,selector,sorter,sampler,joiner,counter,quality,drift,schemer,analyzer}.py`;
  - `undatum/cmds/statistics/`;
  - `undatum/sdk/dataset.py`;
  - benchmarks and budgets.
- Depends on: `update-python-311-duckdb-2` (relation-to-Arrow API of DuckDB 2.0).
- Builds on: `refactor-streaming-operations-core` (operation registry, `to_sql`, contract suite).
- Not changed: CLI options and JSON result layouts. Output records stay identical to the
  Python engine, checked by contract tests.
