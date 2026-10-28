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
- **THEN** the records are written by the iterabledata writer from DuckDB's Arrow batches or the
  Python engine

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
`schema`, `stats`, `quality`, `schema-drift` and `db load` SHALL infer field types with one shared
rule set, and SHALL report the same type for the same field of the same input.

#### Scenario: Same file, same types
- **WHEN** a user runs `schema`, `stats`, `quality` and `schema-drift` on one CSV file
- **THEN** each field has the same inferred type in all four reports

#### Scenario: Text with digits is not probed as a date at length
- **WHEN** a column holds hashes, addresses or sentences with numbers
- **THEN** date detection stops after at most 20 non-date values of that column

### Requirement: DuckDB Execution Through Arrow
Operations with a SQL form SHALL run in DuckDB for inputs that DuckDB cannot read natively when
iterabledata can stream the input as Arrow record batches, and the records SHALL be identical to
those of the Python engine.

#### Scenario: Frequency on an Excel sheet
- **WHEN** a user runs `undatum frequency book.xlsx -f region`
- **THEN** DuckDB computes the counts from Arrow batches produced by iterabledata
- **AND** the result equals the result of `--engine python`

#### Scenario: Format without an Arrow adapter
- **WHEN** iterabledata cannot stream the input as Arrow batches
- **THEN** the operation runs on the Python engine as before
