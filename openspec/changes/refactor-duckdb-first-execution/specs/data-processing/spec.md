## ADDED Requirements

### Requirement: Conversion Through DuckDB for Native Formats
With `--engine auto`, `convert` SHALL write the output with DuckDB `COPY` when DuckDB reads the
input and writes the output format natively (CSV/TSV, JSON, JSON Lines, Parquet; plain, gzip or
zstd), and the records SHALL be identical to those of the Python engine.

#### Scenario: CSV to JSON Lines
- **WHEN** a user runs `undatum convert data.csv data.jsonl`
- **THEN** DuckDB writes `data.jsonl`
- **AND** every record equals the record `--engine python` writes, including original CSV text
  and empty values

#### Scenario: Format DuckDB cannot write
- **WHEN** the output format is not written natively by DuckDB (for example XLSX)
- **THEN** the records are written by the iterabledata writer from DuckDB's result batches or
  the Python engine

#### Scenario: Column types DuckDB writes differently
- **WHEN** the result has a column whose values DuckDB `COPY` writes differently from the Python
  writer (for example timestamps in CSV, UUIDs in Parquet)
- **THEN** the records are written by the Python writer
- **AND** dates and the other types `COPY` writes identically keep using `COPY`, with CSV lines
  ending in CRLF as the Python writer ends them

### Requirement: Workload-Based DuckDB Settings
Every DuckDB query SHALL run on a connection made by the shared connection factory. Row-wise and
window operations SHALL use one thread and a bounded memory limit. Aggregations and sorts SHALL
use all CPU cores and DuckDB's default memory limit. `--duckdb-threads`, `--duckdb-memory` and
`--duckdb-temp-dir` SHALL override these defaults for every command.

#### Scenario: Aggregation uses all cores
- **WHEN** a user runs `undatum frequency data.csv -f city` on a machine with 8 cores
- **THEN** the DuckDB query runs with 8 threads

#### Scenario: Row-wise transform stays bounded
- **WHEN** a user runs `undatum rename` on a 1M-row CSV
- **THEN** the DuckDB query runs with one thread and the default 256 MB limit
- **AND** the memory budget of row-wise transforms holds

#### Scenario: Override applies everywhere
- **WHEN** a user passes `--duckdb-memory 2GB` to `stats`, `quality` or `schema-drift`
- **THEN** the DuckDB connection of that command uses a 2 GB memory limit

### Requirement: Profiling in a Few Scans
For DuckDB-readable inputs, `stats` SHALL compute the counts, missing values, lengths and numeric
distributions of all fields in one scan of the input, and exact distinct values and value
dictionaries in scans that each group several fields within a bound on the distinct values they
hold. It SHALL NOT run one query per field and statistic, and its results SHALL equal the
per-field computation.

#### Scenario: Wide file of low-cardinality fields
- **WHEN** a user runs `undatum stats` on a CSV with 24 columns of three values each
- **THEN** the input is scanned once for the per-field statistics and once per four dictionary
  fields (7 scans instead of about 100)

#### Scenario: High-cardinality fields
- **WHEN** several fields have about as many distinct values as there are records
- **THEN** their exact distinct counts are computed in scans of at most 2,000,000 estimated
  distinct values, so DuckDB's memory does not hold every field's values at once

### Requirement: Consistent Type Inference
`schema`, `analyze`, `stats`, `quality` and `schema-drift` SHALL infer field types with one shared
rule set, and SHALL report the same type for the same field of the same input. Values read as text
(CSV, TSV, and records undatum reads itself) SHALL get the first of integer, number, boolean, date
and datetime that at least 95% of their non-empty values convert to, in a sample of 10,000
records; placeholders (`n/a`, `null`, `-`, empty) SHALL count as empty, a value with a leading
zero SHALL make the field a string, and dates SHALL be ISO or day-first (`31.12.2020`,
`31/12/2020`, `31-12-2020`, `2020/12/31`). Typed inputs (JSON, Parquet) SHALL keep their own
types.

#### Scenario: Same file, same types
- **WHEN** a user runs `schema`, `stats`, `quality` and `schema-drift` on one CSV file
- **THEN** each field has the same type in all four reports

#### Scenario: A few bad values
- **WHEN** 2% of a CSV column's values are text and the rest are integers
- **THEN** every command reports the column as an integer

#### Scenario: Numbers as JSON strings
- **WHEN** a JSON Lines field holds strings such as `"2005"`
- **THEN** every command reports the field as a string

### Requirement: DuckDB Execution Through Arrow
Operations with a SQL form, `convert`, `sort`, `uniq` and `frequency` SHALL run in DuckDB for
inputs that DuckDB cannot read natively when pyarrow reads them as Arrow record batches (ORC,
Arrow IPC/Feather), and the records SHALL be identical to those of the Python engine.

#### Scenario: Frequency on an ORC file
- **WHEN** a user runs `undatum frequency events.orc -f region`
- **THEN** DuckDB computes the counts from Arrow batches of the `region` column
- **AND** the result equals the result of `--engine python`, including missing values

#### Scenario: Format without an Arrow reader
- **WHEN** pyarrow cannot read the input as Arrow batches (XLSX, Avro, Feather v1)
- **THEN** the operation runs on the Python engine as before
