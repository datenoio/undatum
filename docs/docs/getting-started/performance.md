---
title: "Performance"
description: "Large-file conversion, DuckDB, and multiprocessing"
---
# Performance and large files

undatum streams by default, but some paths (especially Parquet writes and whole-dataset
operations like sort/dedup) need explicit low-memory behavior for multi-GB inputs.

## Recommended flags

```bash
# Prefer DuckDB spill-to-disk when the format is duckable (csv/jsonl/parquet + gz/zst)
undatum convert huge.jsonl.zst huge.parquet --low-memory

# Force smaller iterabledata write batches even when DuckDB is unavailable
undatum convert data.xml data.parquet --tagname item --low-memory --engine python --batch-size 5000

# Parquet row-group size (iterable path; DuckDB COPY ignores this flag)
undatum convert data.csv data.parquet --row-group-size 100000 --batch-size 50000 --engine python

# Multiprocessing for CPU-bound Python-engine convert (GitHub #18 / P1.8)
# Uses process-pool chunk batches; preserves row order; omit --threads for sequential
undatum convert big.csv out.jsonl --engine python --threads 8

# Parallel rule-file validation / iterable stats
undatum validate data.csv --rules rules.yml --threads 4
undatum stats data.csv --engine python --threads 4

# External merge sort / disk-backed dedup
undatum sort data.jsonl --by ts --low-memory --output sorted.jsonl
undatum dedup data.jsonl --key-fields id --low-memory --output unique.jsonl
```

## Multiprocessing notes

- `--threads N` opts into undatum process-pool chunk parallelism on **Python/iterable**
  paths. Small files may be slower due to process startup overhead.
- DuckDB already parallelizes internally. Prefer `--engine duckdb` / `--duckdb-threads`
  for duckable formats; undatum does **not** wrap DuckDB `COPY` in an extra process pool.
- Bulk directory conversion (`--recursive`) already uses `--threads` as concurrent file workers.
- Order-sensitive whole-file ops (`sort`, global `dedup`) are not parallelized this way.

## Notes

- Gzip-compressed duckable formats are eligible for the DuckDB engine (`gz` / `gzip` codec ids).
- `--low-memory` on convert prefers DuckDB `COPY ... TO` for Parquet/CSV/JSONL when possible.
- Sort automatically spills after ~100k buffered rows; `--low-memory` forces spill immediately.
- Dedup spills unique keys to a temporary SQLite store when the in-memory set grows large, or
  immediately with `--low-memory`.
- Temp files use the system temp directory unless `--duckdb-temp-dir` / temp options are set.
- iterabledata 1.0.17+ keeps Parquet/Arrow writes in bounded batches (`row_group_size` / flush
  batches) and exposes codec profiles `fast` / `balanced` / `max`; `undatum convert --row-group-size`
  forwards the Parquet flush threshold (skips DuckDB COPY); `undatum repack` defaults
  to maximum container or format-native compression.

See also: [Quickstarts](/getting-started/quick-start), [Format support](/formats/).


## Performance tips

1. **Use appropriate formats**: Parquet/ORC/Avro for analytics, JSONL for streaming
2. **DuckDB engine**: Pass `--engine duckdb` on `stats`, `select`, `count`, `sort`, `join`, and related commands for accelerated tabular workloads
3. **Multiprocessing (`--threads N`)**: For Python-engine `convert`, `validate` (rules), `stats`, and `frequency`, use process-pool chunk parallelism on multi-core machines. Example: `undatum convert big.csv out.jsonl --engine python --threads 8`. Prefer DuckDB for duckable formats instead of nesting pools. See [performance](/getting-started/performance).
4. **Compression**: Use ZSTD or GZIP for better compression ratios
5. **Chunking**: Split large files for parallel processing, or use `--batch-size` with `--threads`
6. **Filtering**: Apply filters early (`select --filter`, `search`) to reduce data volume; DuckDB pushdown is used when possible
7. **Streaming**: undatum streams data by default for low memory usage
8. **AI documentation**: Prefer `ai doc` for block-based output; use local providers (Ollama/LM Studio) for zero-cost runs
9. **Cloud I/O**: Read/write directly from `s3://`, `gs://`, or `az://` URIs instead of staging files locally
