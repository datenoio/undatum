## ADDED Requirements

### Requirement: Lean DuckDB Path
A command that DuckDB runs (natively for CSV, TSV, JSON, JSON Lines and Parquet input) SHALL
NOT import iterabledata, pyarrow, pandas, openpyxl or polars, unless an option asks for a reader
or writer only they provide. Format detection SHALL recognise common file extensions without
iterabledata.

#### Scenario: Frequency on a small CSV
- **WHEN** a user runs `undatum frequency -f name data.csv` on a small file
- **THEN** the command finishes in about the time of `undatum count data.csv`
- **AND** iterabledata, pyarrow and pandas are not imported

#### Scenario: Statistics on a CSV
- **WHEN** a user runs `undatum stats data.csv`
- **THEN** the type sample is read by DuckDB with the values the Python reader gives
- **AND** pandas and iterabledata are not imported

#### Scenario: Python engine
- **WHEN** a command reads its input with the Python engine (`--engine python`, or a format
  DuckDB does not read)
- **THEN** iterabledata is imported when the input is opened
