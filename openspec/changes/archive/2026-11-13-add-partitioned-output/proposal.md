# Change: Hive-Style Partitioned Output for split and convert

## Why
`split --fields <f>` already writes one file per distinct value combination into `--dirname`, but
it produces flat file names, keeps every partition writer in one process without a limit, and is
not available from `convert`. Data engineers need Hive-style partitioned output
(`year=2026/month=10/part-0.parquet`) in any writable format for DuckDB, Spark, Athena and
BigQuery external tables, with predictable behaviour for high-cardinality keys.

## What Changes
- `split --fields <f> --hive` writes `<dirname>/<field>=<value>/part-N.<ext>`.
- `convert --partition-by <fields> <input> <dir>` writes Hive-partitioned output in any writable
  format; DuckDB `COPY … (PARTITION_BY …)` when the input is DuckDB-readable, the streaming writer
  pool otherwise.
- `--max-open-files` (default 128) for both commands, with close-and-append for high-cardinality
  keys; key values are sanitized for file systems (`/`, empty, null → `__null__`).

## Impact
- Affected specs: `data-processing`
- Affected code: `undatum/cmds/` split implementation, `convert`, `undatum/io/` sink
  (partitioning hook)
- Depends on: `refactor-streaming-operations-core`
