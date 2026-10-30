# Change: pandas Becomes an Optional Extra

## Why
pandas is a base dependency, but after the DuckDB-first work little in undatum needs it. pandas is
44 MB installed (plus `python-dateutil`), and `import pandas` took 0.55–0.7 s on every
`stats`, `schema` and `analyze` run until `update-duckdb-path-startup`. The remaining uses are:
- `analyze` and `schema --flatten-nested` build a DataFrame of the records undatum reads itself
  (XML, JSON through the Python reader, flattened records) for DuckDB to describe.
- `analyze --autodoc` turns its sample into CSV text with DuckDB's `fetchdf()`.
- `db query --format-out parquet` writes Parquet with `DataFrame.to_parquet`.
- `extract` builds tables as DataFrames, writes them with pandas and reads Excel with
  `read_excel`.
- `Dataset.to_pandas()` returns pandas frames.
- `analyze --use-pandas` asks for pandas by name.
- The DuckDB ingester falls back to `conn.append(DataFrame)` without a native appender.

iterabledata and the other base dependencies do not require pandas. This is item 17 of the October
2026 engine review (`analysis/2026-10-28-undatum-engines-and-competitors.md`).

## What Changes
- **BREAKING (packaging):** `pandas` moves from `dependencies` to a new `pandas` extra.
  `extract` and `all` include it, so `undatum[extract]` and `undatum[all]` behave as before.
  `dev` lists it for the tests.
- **Records as Arrow:** a new `undatum.io.arrow.records_table()` builds a `pyarrow.Table` from
  dict records (one column per field in first-seen order; a missing field is null). A field
  whose values Arrow cannot hold in one type either raises an `UndatumError` or is kept as text
  on request. It replaces the DataFrame in `analyze`, `schema --flatten-nested` and
  `db query` Parquet output, and the SDK's record batches use it.
- **Type changes** in `analyze` and `schema` for records undatum reads itself, which now match
  DuckDB reading the same data as JSON:
  - integers with missing values are `BIGINT`; pandas made them `DOUBLE`;
  - nested objects are `STRUCT`s with typed members; pandas gave
    `MAP(VARCHAR, VARCHAR)`;
  - lists of integers are `BIGINT[]` (were `INTEGER[]`).
- The `analyze --autodoc` sample is written with the csv module.
- **Commands that still need pandas** import it only when they run, and exit with code 2 and
  `pip install "undatum[pandas]"` (`undatum[extract]` for `extract`) when it is missing:
  - `extract`;
  - `analyze --use-pandas`;
  - `Dataset.to_pandas()`.
- `tests/test_base_install_imports.py` blocks pandas, as it blocks the other extras.

## Impact
- Affected specs: `distribution` (extends Lean Base Install).
- Affected code: `pyproject.toml`, `undatum/io/arrow.py` (new), `undatum/cmds/{analyzer,schemer,db_query,extractor}.py`,
  `undatum/sdk/dataset.py`, `undatum/common/schema_utils.py`, tests and documentation.
- Users who use pandas through undatum without the `extract` or `all` extra install
  `undatum[pandas]`.
