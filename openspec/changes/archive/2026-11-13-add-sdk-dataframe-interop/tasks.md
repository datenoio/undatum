## 1. SDK
- [x] 1.1 Arrow-table sources (`SourceSpec.table`): Python rows from `to_pylist()`, DuckDB plans
      on the registered table
- [x] 1.2 `Dataset.from_frame()` and `Dataset.to_frame()` through Narwhals (`narwhals.stable.v2`)
- [x] 1.3 `narwhals>=2.0,<3` dependency, `uv.lock`, conda recipe

## 2. Verification
- [x] 2.1 Tests: pyarrow, pandas, Polars, Polars lazy and DuckDB relations give the same results
      on both engines; `to_frame()` for pyarrow, pandas and Polars; errors
- [x] 2.2 SDK documentation and reference, changelog
