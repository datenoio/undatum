## 1. Imports
- [x] 1.1 `open_iterable` wrappers in `common/s3_iterable.py` and `common/db_source.py` import
      iterabledata on first use
- [x] 1.2 pandas, qddate and openpyxl imported in the functions that use them (`schema_utils`,
      `schemer`, `analyzer`, `statistics`)
- [x] 1.3 `convert`: write-capability suggestions built only for error messages, known writable
      formats skip the probe, pyarrow found with `importlib.util.find_spec`, `CopyResult` for
      the DuckDB path

## 2. Detection without iterabledata
- [x] 2.1 `detect_engine()`, `get_file_type()`, `schema`, `analyze` and `stats` recognise common
      extensions from the name
- [x] 2.2 `headers` reads CSV fields from the header line; `stats` reads its CSV type sample
      through DuckDB

## 3. Verification
- [x] 3.1 `tests/test_startup_imports.py`: 20 DuckDB-path command/input pairs import none of
      iterabledata, pyarrow, pandas, openpyxl, polars
- [x] 3.2 Startup measured before and after for every command; full suite and benchmarks
