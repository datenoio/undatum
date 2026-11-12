# querying Specification

## Purpose
DuckDB-accelerated `select`/`frequency`/`uniq` with iterable fallback, and
comparison/boolean `--filter` expressions (no MistQL). Ad-hoc SQL is `undatum sql`.
## Requirements
### Requirement: DuckDB-accelerated select with safe fallback
The system SHALL support a DuckDB execution path for the `select` command on
duckable formats, and SHALL fall back to the iterable path when DuckDB cannot be
used.

#### Scenario: DuckDB path for compatible input
- **WHEN** the input format is duckable and engine is `auto`
- **THEN** the system uses DuckDB to select the requested fields

#### Scenario: Fallback when DuckDB is unavailable or fails
- **WHEN** DuckDB is unavailable, errors, or the input format is not duckable
- **THEN** the system falls back to the iterable path without aborting

### Requirement: Explicit engine override for select
The system SHALL allow users to force the `select` execution engine via a CLI
option.

#### Scenario: User forces iterable engine
- **WHEN** the user passes `--engine iterable`
- **THEN** the system uses the iterable path even if DuckDB is available

### Requirement: Filter handling across engines
The system SHALL apply comparison and boolean filter expressions in `select`,
`frequency`, and `uniq` on both execution paths, translating filters to SQL
where safe and otherwise evaluating the same subset on the iterable path.
Boolean operators `AND`/`OR` and `&&`/`||` are both accepted, as are single-
and double-quoted strings. The system SHALL NOT depend on mistql.

#### Scenario: Filter translated to SQL for DuckDB
- **WHEN** a filter expression is provided and is safely translatable to SQL
- **THEN** the system applies it in the DuckDB query for `select`, `frequency`, and `uniq`

#### Scenario: Filter not translatable to SQL
- **WHEN** a filter expression cannot be safely translated to SQL (`IN`, `LIKE`, `match`, nested dotted fields)
- **THEN** the system SHALL reject the expression
- **AND** SHALL tell the user to use `undatum sql` for SQL-only constructs

### Requirement: Bounded batching during selection
The system SHALL flush output in fixed-size batches to avoid unbounded memory
growth.

#### Scenario: Large input with default batching
- **WHEN** processing large input files
- **THEN** the system flushes output at the configured batch size

### Requirement: Required fields validation
The system SHALL validate that the `fields` option is provided for `select`.

#### Scenario: Missing fields option
- **WHEN** the user omits `fields`
- **THEN** the system returns a clear error before processing begins

### Requirement: Row Filter Expressions
Commands that read records SHALL accept `--where` with a SQL boolean expression and SHALL output
only rows for which the expression is true, for every supported input format.

#### Scenario: Filter JSON Lines with SQL
- **WHEN** user runs `undatum select data.jsonl --where "amount > 100 AND city = 'Berlin'" -o out.csv`
- **THEN** `out.csv` contains only matching rows

#### Scenario: Unknown column
- **WHEN** user runs `undatum select data.csv --where "amout > 100"`
- **THEN** the command exits with code 1 and suggests `amount`

### Requirement: Computed Columns
`select` and `convert` SHALL accept repeatable `--add "name = expression"` options that append
columns computed from SQL expressions.

#### Scenario: Add total column
- **WHEN** user runs `undatum convert orders.csv orders.parquet --add "total = price * qty"`
- **THEN** each output row has a `total` column equal to `price * qty`

