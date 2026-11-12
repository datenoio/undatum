## ADDED Requirements

### Requirement: DataFrame Interoperability
The SDK SHALL accept a DataFrame of any library Narwhals supports as a dataset source
(`Dataset.from_frame`), collecting lazy frames, and SHALL return a dataset's records as a native
frame of a chosen library (`Dataset.to_frame`). Plans on a frame SHALL give the same records with
DuckDB as with the Python engine.

#### Scenario: pandas in, Polars out
- **WHEN** a user runs `Dataset.from_frame(pandas_df).filter(query="amount > 10").to_frame("polars")`
- **THEN** the result is a Polars DataFrame of the matching records

#### Scenario: Lazy frame
- **WHEN** a user passes a Polars `LazyFrame` or a DuckDB relation to `Dataset.from_frame`
- **THEN** it is collected and its records become the dataset's records

#### Scenario: Missing backend
- **WHEN** a user calls `to_frame("modin")` without Modin installed
- **THEN** a `DependencyError` names the missing package
