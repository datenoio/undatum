## 1. Writer
- [x] 1.1 Add `write_records(path, records, fieldnames=None, **iterableargs)` in
      `undatum/common/` that uses `open_iterable(..., mode="w")` and streams records
      (`undatum/common/writer.py`: `RecordSink`, `write_records`, `emit_records`,
      `duckdb_copy_to_file`)
- [x] 1.2 Raise `FormatError` for non-writable formats before creating the file; remove partial
      files on failure
- [x] 1.3 Compute CSV/TSV headers from the union of keys in first-seen order

## 2. Commands
- [x] 2.1 Switch `rename`, `fill`, `replace`, `enum`, `head`, `tail`, `reverse`, `search`,
      `explode`, `join`, `cat`, `fixlengths`, `transpose` to the new writer
- [x] 2.2 Keep `DataWriter` for stdout only and document it as such

## 3. Tests and specs
- [x] 3.1 Add `tests/test_output_contract.py` parametrized over command × output format
- [x] 3.2 Assert exit code 0 and non-empty, readable output for every supported pair; assert
      exit code 1 and no file for an unsupported pair
- [x] 3.3 Update `docs/docs/commands/*.md` examples to show a non-CSV output once
- [x] 3.4 Route DuckDB `COPY` outputs of sort, dedup, slice, join and select through
      `duckdb_copy_to_file` (escaped path, `.json` as array, atomic write)
- [x] 3.5 Move `uniq`, `frequency` and `fmt` file output to the shared writer
