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

## Which commands use DuckDB

DuckDB reads CSV, TSV, JSON, JSON Lines and Parquet (plain or `.gz`/`.zst`), and ORC and Arrow
IPC/Feather v2 files through pyarrow. With the default `--engine auto`, these commands run on
such inputs as DuckDB queries, which spill to disk on their own. Aggregations and sorts use
every core; row commands use one thread, since reading and writing bound them. Other inputs,
and options DuckDB cannot apply (`--table`, `--sheet`, `--flatten-nested`,
`--on-error skip|warn`, XML tags), use the Python engine.

| Commands | With `--engine auto` | ORC, Arrow/Feather |
|----------|----------------------|--------------------|
| `rename`, `fill`, `replace`, `search`, `head`, `slice`, `select`, `--where`, `--add` | one DuckDB query for every step, with the records of the Python engine (contract tests) | DuckDB |
| `convert` | one `COPY` for CSV and Parquet output, and for JSON Lines when the text equals the Python writer's | DuckDB |
| `sort`, `uniq`, `frequency` | DuckDB | DuckDB |
| `count` | DuckDB | the row count stored in the file (also DBF) |
| `stats`, `schema`, `analyze`, `join`, `sample` | DuckDB | Python reader |
| `quality`, `schema-drift` | DuckDB; inputs DuckDB cannot read are loaded into it by the Python reader | Python reader |
| `sql` | DuckDB, with each file as a view (formats DuckDB reads by name) | not read |
| `dedup`, `reverse` | Python (bounded memory); DuckDB with `--engine duckdb` | DuckDB with `--engine duckdb` |
| `cat`, `enum`, `explode`, `exclude`, `fixlengths`, `mask`, `tail`, `transpose`, `validate` | Python, streaming | Python |

The [Python SDK](/integrations/sdk) runs `count()`, `head()`, `uniq()`, `frequency()`,
`schema()`, `write()` and the Arrow and DataFrame exports of a plan as one DuckDB query on the
same terms.

Measured on 1M rows (macOS arm64, Python 3.11, median of three runs), before the DuckDB-first
work (October 2026) and now:

| Command (1M rows) | Before | Now |
|-------------------|-------|-----|
| `stats data.csv` | 252 s, 508 MB | 2.4 s, 550 MB |
| `convert data.parquet data.jsonl` | 4.3 s, 346 MB | 1.2 s, 184 MB |
| `convert data.orc data.parquet` | 4.9 s, 315 MB | 1.2 s, 492 MB |
| `convert data.csv data.parquet` | 1.2 s, 791 MB | 1.4 s, 331 MB |
| `select data.csv -f id,amount -o s.csv` | 0.85 s, 318 MB | 0.68 s, 181 MB |
| `rename data.csv -o r.csv` | 1.0 s, 127 MB | 0.7 s, 178 MB |
| `dedup data.csv --key-fields city` | 2.7 s, 166 MB | 2.5 s, 121 MB |
| `sort`, `frequency`, `uniq`, `count`, `head`, `sql` | 0.2-1.0 s | the same time, 10-65 MB more |

DuckDB 2.0 connections start about 20 MB larger than DuckDB 1.5, which is most of the memory
added to the short commands.

Details:

- `--where` conditions and `--add` columns on inputs DuckDB cannot read are evaluated in
  batches with the same results.
- `convert` writes the records of the Python engine, checked by contract tests: CSV values stay
  text and empty CSV fields stay empty strings. JSON Lines written by DuckDB are compact (no
  space after `:` and `,`). Inputs with timestamps, intervals, decimals, 32-bit floats, UUIDs or
  binary values (and, for CSV output, booleans or nested values) are converted by the Python
  engine, whose text differs for them.
- ORC and Arrow inputs are read stripe by stripe or batch by batch, so peak memory grows with
  the stripe size (about 400-470 MB for row commands on 1M rows).

`dedup` and `reverse` use DuckDB only with `--engine duckdb`: DuckDB holds the records up to
its memory limit (about 750 MB for 2M rows), while the default Python engine stays bounded
(spilling to disk). On 2M CSV rows `dedup --engine duckdb` takes 1.6 s instead of 10.6 s, and
`reverse --engine duckdb` 2 s instead of about 30 s; both give the same records.

CSV in another encoding than UTF-8 (for example Windows-1251) goes to the Python engine, which
detects the encoding, unless DuckDB's `encodings` extension is installed
([`undatum extensions install encodings`](/commands/extensions)): then DuckDB reads it in the
encoding the Python engine would use, with the same records. A row DuckDB cannot read makes the command fall back
to the Python engine; if records were already printed to standard output, the command stops
with an error instead, and `--engine python` reads the file.

DuckDB reads CSV field names from the first line, as the Python engine does, with every value as
text; values beyond the header in a longer row are dropped. A header DuckDB cannot use (an empty
name, or names that differ only by case, such as `id,ID`) sends the file to the Python engine.

Commands that run in DuckDB do not import iterabledata, pyarrow or pandas, which takes 0.5-1.2 s:
on a small file `count`, `head`, `frequency`, `uniq`, `sort`, `select`, `headers`, `convert`,
`sample` and `join` start in about 0.25 s, and `stats` and `schema` in about 0.35 s. Commands that
read through the Python engine import iterabledata when they open the input. `--engine python`
forces the streaming Python path, for example to compare results.

## Partitioned output

`convert --partition-by` and `split --fields ... --hive` write Hive-style `field=value/`
directories. CSV and Parquet go through DuckDB `COPY ... PARTITION_BY` (DuckDB 1.5 or later);
other formats use a streaming writer that keeps at most `--max-open-files` files open
(default 128), so keys with many distinct values work too:

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
