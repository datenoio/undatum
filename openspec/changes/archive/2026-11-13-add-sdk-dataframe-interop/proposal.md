# Change: DataFrames of Any Library In and Out of the SDK (Narwhals)

## Why
The SDK reads files and in-memory records, and exports to Arrow, pandas, Polars and Dask with one
method each (`refactor-duckdb-first-execution`, task 7). A DataFrame cannot go into a
`Dataset`: users convert it to records first, which loses the column types and runs the plan in
Python. Other libraries (Modin, cuDF, DuckDB relations, Ibis) need their own code paths.
[Narwhals](https://narwhals-dev.github.io/narwhals/) is a dependency-free compatibility layer over
these libraries. This is item 15 of the October 2026 engine review
(`analysis/2026-10-28-undatum-engines-and-competitors.md`).

## What Changes
- **`Dataset.from_frame(frame)`:** wraps any eager frame Narwhals supports (pandas, Polars,
  PyArrow, Modin, cuDF, ...) through Arrow.
  - Lazy frames (a Polars `LazyFrame`, a DuckDB relation, Ibis) are collected first.
  - The `Dataset` keeps the `pyarrow.Table` as its source.
  - Plans on it run in DuckDB (the table is registered on the connection) with the values the
    Python engine reads from it (`to_pylist()`), by the typed-format rules of the Arrow bridge.
- **`Dataset.to_frame(backend, chunksize=None)`:** returns the records as a native frame of
  `backend` (`"pandas"`, `"polars"`, `"pyarrow"`, `"modin"`, `"cudf"`, ...) through `to_arrow()`
  and Narwhals. A missing backend raises `DependencyError`.
- **Dependency:** `narwhals>=2.0,<3` becomes a base dependency (pure Python, no dependencies,
  2.3 MB). It is imported only by these two methods.

## Impact
- Affected specs: `sdk`.
- Affected code: `pyproject.toml`, `undatum/sdk/dataset.py`, tests and documentation.
