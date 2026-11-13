# Change: SQL Expressions for Filtering and Computed Columns

## Why
Row filtering is limited to regex `search` and simple comparison `--filter` expressions; computed
columns require a Python script for `apply` (executed with `runpy`). Users who know SQL must
switch to `undatum sql` and lose format-preserving output. DuckDB is already a dependency and can
evaluate expressions for every DuckDB-readable source.

## What Changes
- `--where "<SQL boolean expression>"` on `select`, `search`, `head`, `sample`, `count` and
  `convert`.
- `--add "name = <SQL expression>"` (repeatable) on `select` and `convert` to add computed columns.
- Expressions are evaluated by DuckDB; for sources DuckDB cannot read, rows are streamed into
  DuckDB in batches (Arrow) so semantics stay identical.
- Expressions are validated up front (parse and column check) with field-name suggestions.

## Impact
- Affected specs: `querying`
- Affected code: `undatum/ops/` (from `refactor-streaming-operations-core`), `select`, `search`,
  `convert` CLI wrappers, docs
- Depends on: `refactor-streaming-operations-core`
