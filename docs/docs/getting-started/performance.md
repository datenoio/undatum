---
title: "Performance"
description: "Large-file conversion, DuckDB, and multiprocessing"
---
# Performance and large files

undatum streams by default: record commands read and write one record at a time, so their
memory does not grow with the input. Whole-dataset operations (sort, dedup, reverse) keep a
bounded buffer and spill to disk, and a few commands hold the values they count.

## Memory by command

Every command page starts its reference with a capabilities line that states the memory
profile. In short:

| Memory | Commands |
|--------|----------|
| Streaming (does not grow with the input) | `convert`, `cat`, `select`, `search`, `rename`, `replace`, `fill`, `enum`, `explode`, `mask`, `split`, `validate`; `apply`, `fixlengths` and `fmt` read the input twice |
| Bounded | `head`, `tail` and `sample` (`--limit` rows), `slice` (stops after the last record), `analyze`, `schema`, `sniff` (a sample) |
| Bounded, then disk | `sort` (100k rows, then external merge sort), `dedup` (100k keys, then a disk index), `reverse` (chunks of 50,000 records), `fill --strategy backward` |
| Keys in memory | `exclude` (keys of the exclusion file), `join` with the Python engine (the second file), `diff` (keys of both files) |
| Grows with distinct values | `frequency`, `uniq`, distinct counts in `stats` |
| One output record at a time | `transpose` (reads the input once per field) |

On 1M rows `rename` peaks at about 150 MB; CI fails when a streaming command goes over 300 MB
on 1M rows (see [benchmarks](/development/benchmarks)).

## DuckDB pushdown

On CSV, TSV, JSON, JSON Lines and Parquet inputs (plain or `.gz`/`.zst`) the default
`--engine auto` runs these as one DuckDB query, which spills to disk on its own:

- `rename`, `fill`, `replace`, `search`, `head` and `slice` — the same records as the Python
  engine, checked by contract tests (`rename` is about 7x faster on 1M CSV rows);
- `select`, `sort`, `dedup`, `join`, `count`, `stats`, `frequency`, `uniq` and `sql`;
- `--where` conditions and `--add` columns. Inputs DuckDB cannot read are evaluated in batches
  with the same results.

Commands that read and write these formats through DuckDB do not import iterabledata at all,
which saves about a second per run (`undatum head data.csv` takes 0.7 s). `--engine python`
forces the streaming Python path, for example to compare results.

## Partitioned output

`convert --partition-by` and `split --fields ... --hive` write Hive-style `field=value/`
directories. CSV and Parquet go through DuckDB `COPY ... PARTITION_BY`; other formats use a
streaming writer that keeps at most `--max-open-files` files open (default 128), so keys with
many distinct values work too:

```bash
undatum convert data.csv by_country --partition-by country -O parquet
```

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

## Performance tips

1. **Use appropriate formats**: Parquet/ORC/Avro for analytics, JSONL for streaming
2. **DuckDB engine**: Keep the default `--engine auto` on CSV/TSV/JSON/JSON Lines/Parquet; it uses DuckDB where a command supports it (see [DuckDB pushdown](#duckdb-pushdown))
3. **Multiprocessing (`--threads N`)**: For Python-engine `convert`, `validate` (rules), `stats`, and `frequency`, use process-pool chunk parallelism on multi-core machines (see [multiprocessing notes](#multiprocessing-notes)). Prefer DuckDB for duckable formats instead of nesting pools
4. **Compression**: Use ZSTD or GZIP for better compression ratios
5. **Chunking**: Split large files for parallel processing, or use `--batch-size` with `--threads`
6. **Filtering**: Apply filters early (`--where`, `select --filter`, `search`) to reduce data volume; DuckDB pushdown is used when possible
7. **Pipelines**: `-` reads standard input, so commands chain without temporary files (`undatum sort - --by a | undatum head - -n 3`); closing the pipe early (`| head -1`) stops reading
8. **AI documentation**: Prefer `ai doc` for block-based output; use local providers (Ollama/LM Studio) for zero-cost runs
9. **Cloud I/O**: Read/write directly from `s3://`, `gs://`, or `az://` URIs instead of staging files locally

See also: [Quick start](/getting-started/quick-start), [Format support](/formats/), [Benchmarks](/development/benchmarks).
