## ADDED Requirements

### Requirement: Arrow Interchange
`Dataset` SHALL provide `to_arrow()`, and `to_polars()` and `to_pandas()` SHALL build their frames
from Arrow data without materialising the records as a list of Python dicts.

#### Scenario: Plan to Polars
- **WHEN** a user calls `Dataset("data.csv").select(["a", "b"]).to_polars()`
- **THEN** the frame is built from Arrow record batches produced by DuckDB or iterabledata

#### Scenario: Arrow table
- **WHEN** a user calls `Dataset("data.parquet").to_arrow()`
- **THEN** a `pyarrow.Table` (or record batch reader) with the dataset's columns is returned

### Requirement: SQL Execution of Analysis Methods
`Dataset.count()`, `head()`, `uniq()`, `frequency()` and `schema()` SHALL run as one DuckDB query
when the source is DuckDB-readable and every plan step has a SQL form, with the same results as
the Python engine.

#### Scenario: Frequency on CSV
- **WHEN** a user calls `Dataset("data.csv").frequency(["city"])`
- **THEN** DuckDB computes the counts in one query
- **AND** the result equals the Python engine's result
