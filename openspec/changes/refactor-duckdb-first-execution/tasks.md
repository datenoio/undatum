## 1. Decision
- [ ] 1.1 Approve DuckDB-first execution with Arrow interchange (no Polars engine)
- [ ] 1.2 Decide how Excel is read (DuckDB `excel` extension or `fastexcel`)

## 2. Connection factory and workload classes
- [ ] 2.1 Workload classes in `create_duckdb_connection` (row-wise: 1 thread / 256 MB;
      aggregate/sort: all cores / DuckDB default), `--duckdb-*` overrides, temp directory
- [ ] 2.2 Move `stats`, `count`, `analyze`, `schema`, `quality`, `drift`, `ops/expr.py` off the
      global `duckdb.sql()` / bare `duckdb.connect()`
- [ ] 2.3 One escaped read-expression builder; remove the `read_csv_auto('{path}')` copies in
      `selector.py`, `sampler.py`, `joiner.py`, `converter.py`

## 3. Conversion through DuckDB
- [ ] 3.1 `detect_engine` treats `convert` as SQL-expressible for native in/out pairs
- [ ] 3.2 `COPY` for CSV/TSV, JSON Lines, Parquet outputs with Python-equal text (temporal and
      NULL formatting)
- [ ] 3.3 Contract tests: every native input × output pair, both engines, identical records

## 4. Type inference and stats
- [ ] 4.1 Shared type-inference module (TRY_CAST shares, `could_be_date` + qddate for leftovers)
- [ ] 4.2 Use it in `schema`, `stats`, `quality`, `schema-drift`, `db load`; remove the old rules
- [ ] 4.3 `stats` in at most two scans (aggregate query + grouped dictionary query)
- [ ] 4.4 Test: the same file gives the same field types in all four commands

## 5. Output without dicts
- [ ] 5.1 `write_query` writes Arrow batches to the iterabledata writers for non-`COPY` formats
- [ ] 5.2 `uniq`, `frequency`, `sql` stop materialising results with `fetchall`
- [ ] 5.3 Remove the `_TEMPORAL` exclusion once temporal text matches

## 6. Arrow bridge
- [ ] 6.1 `RowSource.arrow_reader()` for formats with an iterabledata Arrow adapter
- [ ] 6.2 Runner registers the reader in DuckDB when `duckdb_from()` is `None`
- [ ] 6.3 Contract tests on XLSX, Avro and ORC inputs
- [ ] 6.4 Remove the per-command DuckDB code paths covered by the ops registry

## 7. SDK
- [ ] 7.1 `count`, `head`, `uniq`, `frequency`, `schema` compile to SQL; reuse
      `ops.runner.compose_sql` instead of `Dataset._sql_query`
- [ ] 7.2 `to_arrow()`; `to_polars()` / `to_pandas()` through Arrow
- [ ] 7.3 SDK reference regenerated (`scripts/generate_sdk_reference.py`)

## 8. Verification
- [ ] 8.1 Benchmarks (`scripts/benchmarks.py`) against the base branch for every step; update
      `tests/benchmarks/budgets.toml`
- [ ] 8.2 Memory budget suite unchanged for streaming commands
- [ ] 8.3 `docs/docs/getting-started/performance.md` lists which commands use DuckDB
- [ ] 8.4 `openspec validate refactor-duckdb-first-execution --strict`
