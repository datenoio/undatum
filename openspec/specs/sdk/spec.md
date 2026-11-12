# sdk Specification

## Purpose
Fluent Python `Dataset` API that mirrors CLI transforms for programmatic read, transform, and write workflows.
## Requirements
### Requirement: Dataset Class
The system SHALL provide a `Dataset` class as the primary interface for programmatic data
processing.

#### Scenario: Read data into Dataset
- **WHEN** user calls `ds = Dataset.read("data.jsonl")`
- **THEN** Dataset instance is created with data loaded from file

#### Scenario: Write Dataset to file
- **WHEN** user calls `ds.write("output.parquet")`
- **THEN** Dataset data is written to specified file

### Requirement: Transform Methods
The Dataset class SHALL provide transform methods that map to CLI commands.

#### Scenario: Fill missing values
- **WHEN** user calls `ds = ds.fill("age", value=0)`
- **THEN** missing values in "age" field are filled with 0, returning new Dataset instance

#### Scenario: Deduplicate records
- **WHEN** user calls `ds = ds.dedup(keys=["user_id"])`
- **THEN** duplicate records based on user_id are removed, returning new Dataset instance

#### Scenario: Sort data
- **WHEN** user calls `ds = ds.sort(key="age", reverse=True)`
- **THEN** data is sorted by age field in descending order, returning new Dataset instance

### Requirement: Method Chaining
Dataset transform methods SHALL support method chaining for fluent pipeline syntax.

#### Scenario: Chain multiple transforms
- **WHEN** user calls `ds = Dataset.read("data.jsonl").fill("age", 0).dedup(keys=["id"]).sort(key="age")`
- **THEN** all transforms are applied in sequence, returning final Dataset instance

### Requirement: Analysis Methods
The Dataset class SHALL provide analysis methods that return results rather than new Dataset
instances.

#### Scenario: Compute statistics
- **WHEN** user calls `stats = ds.stats()`
- **THEN** statistics object is returned with computed statistics

#### Scenario: Count records
- **WHEN** user calls `count = ds.count()`
- **THEN** integer count of records is returned

### Requirement: Consistent Behavior
SDK methods SHALL behave consistently with corresponding CLI commands.

#### Scenario: SDK matches CLI behavior
- **WHEN** same operation is performed via SDK and CLI
- **THEN** results are identical

### Requirement: Temporary File Lifecycle
The SDK SHALL delete every temporary file it creates for chained operations once the file is no
longer needed, and no later than when the `Dataset` is closed or the interpreter exits.

#### Scenario: Chain leaves no files behind
- **WHEN** user runs `Dataset.read("data.csv").fill("a", value=0).dedup().write("out.jsonl")`
- **THEN** no temporary files created by the chain remain after `write` returns

#### Scenario: Context manager
- **WHEN** user uses `with Dataset.read("data.csv") as ds:` and exits the block
- **THEN** all temporary files of `ds` are removed

### Requirement: Lazy Execution Plan
Transform methods on `Dataset` SHALL record operations without reading data, and the plan SHALL
execute once when results are requested (write, iteration, count, statistics or DataFrame export).

#### Scenario: Building a chain reads nothing
- **WHEN** user calls `Dataset.read("big.csv").fill("a", value=0).dedup()`
- **THEN** no records are read until a terminal method is called

### Requirement: No Intermediate Files Between Steps
Executing an SDK chain SHALL stream records between steps without writing intermediate files,
except for operations that must spill to disk internally.

#### Scenario: Three-step chain
- **WHEN** user runs `Dataset.read("data.csv").rename(...).fill(...).write("out.parquet")`
- **THEN** no intermediate JSONL files are created

### Requirement: Typed Values Preserved Between Steps
Values SHALL keep their Python types between SDK steps and SHALL be converted only by the final
sink.

#### Scenario: Dates survive a chain
- **WHEN** a Parquet source has a date column and the user chains `rename` and `sort`
- **THEN** iterating the result yields `datetime.date` values for that column

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

