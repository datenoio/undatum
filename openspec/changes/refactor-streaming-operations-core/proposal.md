# Change: Streaming Operations Core and Unified I/O Layer

## Why
Each command is a class that receives an untyped `options` dict and decides on its own how to
read, compute and write. Three execution paths coexist: the iterabledata converter (streaming),
DuckDB (only for csv/jsonl/json/parquet with gz/zst, `undatum/constants.py:95-97`), and a
"collect into a list → normalize copy → `DataWriter`" block copied across 20 modules (example:
`undatum/cmds/renamer.py:30-119`). About 15 of these hold the whole dataset in memory twice.
Measured on the same CSV, `rename` peaks at 357 / 507 / 800 MB for 250k / 500k / 1M rows while
`convert` stays at 278 MB; a 10-row `head` already costs 216 MB. S3 reads download the whole
object to a temp file (`undatum/common/s3_iterable.py:217-222`). `undatum/cmds/converter.py:493-525`
monkeypatches `iterable.convert.core.open_iterable` at runtime to inject codec arguments. This
layout produced defect #1, the memory growth and the drift between CLI, SDK and MCP.

## What Changes
- New `undatum/ops/` package: each operation = typed config (frozen dataclass) + a streaming
  function `Iterable[dict] → Iterator[dict]` + optional SQL implementation for DuckDB + metadata
  (streaming class, required full passes, supported engines).
- New `undatum/io/` layer: `open_source()` (files, stdin, cloud URIs, database sources) and
  `open_sink()` (any writable iterabledata format, stdout, compression, partitioning hook) used
  by every command.
- Engine pushdown: for DuckDB-readable inputs, `rename`, `fill`, `replace`, `search`, `select`,
  `enum`, `head`, `tail`, `count` run as SQL (`SELECT * RENAME`, `COALESCE`,
  `regexp_replace`, `row_number()`), with the streaming Python path as fallback.
- Bounded-memory budgets per operation class, enforced by tests (see
  `add-performance-benchmarks`): row-wise ≤ 300 MB peak RSS for 1M rows; whole-dataset operations
  (`reverse`, `transpose`, `sort` without DuckDB) spill to disk.
- Streaming S3 reads through fsspec, like GCS and Azure.
- Upstream to iterabledata: writing to open file objects (replaces `DataWriter`), `codecargs` in
  `iterable.convert` (removes the monkeypatch), stdin reading; bound `iterabledata>=1.0.21,<1.1`.
- Migrate commands one by one; each migration adds the operation to the contract test matrix.

## Impact
- Affected specs: `data-processing`, `cloud-connectors`
- Affected code: new `undatum/ops/`, `undatum/io/`; `undatum/cmds/*`, `undatum/common/iterable.py`,
  `undatum/common/s3_iterable.py`, `undatum/cmds/converter.py`, `undatum/common/engine_selector.py`
- Depends on: `fix-transform-output-writing`, `update-ci-enforcement`
