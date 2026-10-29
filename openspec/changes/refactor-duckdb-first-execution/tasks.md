## 1. Decision
- [x] 1.1 Approve DuckDB-first execution with Arrow interchange (no Polars engine)
- [ ] 1.2 Decide how Excel is read (DuckDB `excel` extension or `fastexcel`)

## 2. Connection factory and workload classes
- [x] 2.1 Workload classes in `create_duckdb_connection` (row-wise: 1 thread / 256 MB;
      aggregate/sort: all cores / DuckDB default), `--duckdb-*` overrides, temp directory
      (`duckdb_connection(options, workload)`; `--duckdb-*` options added to stats, count, uniq,
      analyze, schema, quality and schema-drift)
- [x] 2.2 Move `stats`, `count`, `analyze`, `schema`, `quality`, `drift`, `ops/expr.py` off the
      global `duckdb.sql()` / bare `duckdb.connect()`
- [x] 2.3 One escaped read-expression builder; remove the `read_csv_auto('{path}')` copies in
      `selector.py`, `sampler.py`, `joiner.py`, `converter.py`

## 3. Conversion through DuckDB
- [x] 3.1 `detect_engine` treats `convert` as SQL-expressible for native in/out pairs
- [x] 3.2 `COPY` for CSV/TSV, JSON Lines, Parquet outputs with Python-equal text (temporal and
      NULL formatting) — one thread / 256 MB; types DuckDB writes differently stay on Python
- [x] 3.3 Contract tests: every native input × output pair, both engines, identical records

## 4. Type inference and stats
- [x] 4.1 Shared type-inference module (`common/field_types.py`: TRY_CAST and day-first date shares,
      95%, typed inputs keep their types)
- [x] 4.2 Use it in `schema`, `analyze`, `stats` (both engines), `quality`, `schema-drift`; `db load`
      keeps an all-values rule for created columns (follow-up)
- [x] 4.3 `stats` in one aggregate scan plus grouped scans (dictionaries, four fields per scan;
      exact distinct counts within 2M estimated values per scan); output identical
- [x] 4.4 Test: the same file gives the same field types in all four commands

## 5. Output without dicts
- [x] 5.1 `write_query` and the sinks convert each record once (fast path for records of scalars);
      Arrow batches measured no faster than `fetchmany` for the dict writers (see design)
- [x] 5.2 `uniq`, `frequency` stream DuckDB results in batches (`sql` already used `fetchmany`)
- [x] 5.3 Replace the `_TEMPORAL` exclusion with a per-type rule shared with `convert`, tested type
      by type against the Python writer; CSV `COPY` writes CRLF

## 6. Arrow bridge
- [x] 6.1 `RowSource.arrow_reader()` for ORC and Arrow IPC/Feather with pyarrow (iterabledata has
      no Arrow reader API; kept in undatum until it has one)
- [x] 6.2 The ops runner, `convert`, `sort`, `uniq` and `frequency` register the reader in DuckDB
      when `duckdb_from()` is `None` (`RowSource.duckdb_relation()`)
- [x] 6.3 Contract tests on ORC and Arrow/Feather inputs; XLSX and Avro have no Arrow reader and
      stay on Python (Excel: decision 1.2)
- [x] 6.4 `select` runs through the ops registry; its own DuckDB and Python paths are removed
      (`sort`, `sample` and `join` have no SQL form in the registry yet)

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
