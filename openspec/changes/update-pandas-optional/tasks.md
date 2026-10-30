## 1. Packaging
- [x] 1.1 Move `pandas` to a `pandas` extra; add it to `extract`, `all` and `dev`
- [x] 1.2 `tests/test_base_install_imports.py` blocks pandas

## 2. Code
- [x] 2.1 `undatum.io.arrow.records_table()`; the SDK builds record batches with it
- [x] 2.2 `analyze` and `schema --flatten-nested` describe Arrow tables of records; the autodoc
      sample uses the csv module
- [x] 2.3 `db query` writes Parquet with pyarrow
- [x] 2.4 `extract`, `analyze --use-pandas` and `Dataset.to_pandas()` raise `DependencyError` with
      the install hint when pandas is missing

## 3. Verification
- [x] 3.1 Tests without pandas: base install imports, `analyze` on JSON/XML, `schema
      --flatten-nested`, the commands that need pandas exit with code 2
- [x] 3.2 A clean venv with the wheel and no extras runs `analyze`, `schema` and `stats`
- [x] 3.3 Documentation (installation, analyze, extract, SDK) and changelog
