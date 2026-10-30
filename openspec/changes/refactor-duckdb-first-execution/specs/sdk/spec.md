## ADDED Requirements

### Requirement: Arrow Interchange
`Dataset` SHALL provide `to_arrow()`, and `to_polars()` and `to_pandas()` SHALL build their frames
from Arrow data without materialising the records as a list of Python dicts.

#### Scenario: Plan to Polars
- **WHEN** a user calls `Dataset("data.csv").select(["a", "b"]).to_polars()`
- **THEN** the frame is built from Arrow record batches produced by DuckDB
- **AND** the CSV values stay text, as in the Python reader

#### Scenario: Arrow table
- **WHEN** a user calls `Dataset("data.parquet").to_arrow()`
- **THEN** a `pyarrow.Table` with the dataset's columns is returned
- **AND** `to_arrow(chunksize=n)` returns tables of `n` rows (the last may be shorter)

#### Scenario: Records Arrow cannot type
- **WHEN** a field of a plan DuckDB does not run holds numbers in some records and text in others
- **THEN** `to_arrow()` raises an `UndatumError` that names the field
- **AND** `to_pandas()` builds the frame for those records from the records

### Requirement: SQL Execution of Analysis Methods
`Dataset.count()`, `head()`, `uniq()`, `frequency()` and `schema()` SHALL run as one DuckDB query
when the source is DuckDB-readable, every plan step has a SQL form and DuckDB returns the values
the Python reader returns, with the same results as the Python engine; otherwise they SHALL use
the Python engine.

#### Scenario: Frequency on CSV
- **WHEN** a user calls `Dataset("data.csv").frequency(["city"])`
- **THEN** DuckDB computes the counts in one query
- **AND** the result equals the Python engine's result, ties in first-seen order

#### Scenario: JSON values
- **WHEN** a user calls `head()` on a JSON Lines dataset whose strings look like dates
- **THEN** the records come from the Python reader, with the strings unchanged
- **AND** `count()` on the same dataset runs in DuckDB

#### Scenario: Python engine
- **WHEN** a user calls `Dataset.read("data.csv", engine="python").count()`
- **THEN** the records are counted by the Python engine
