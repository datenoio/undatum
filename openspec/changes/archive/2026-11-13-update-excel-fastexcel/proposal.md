# Change: Read Excel and ODS with fastexcel, with typed values

## Why
undatum reads Excel through iterabledata's openpyxl and xlrd readers. They stream every cell as
text: `str(cell.value)`. So a number is `"1"`, a date is `"2021-05-06 00:00:00"`, an empty cell is
the string `"None"`, and a formula cell is its formula (`"=B3*2"`, the workbook is not opened
with `data_only`). A column with an empty header is dropped. Reading is slow: 100k rows take
1.2 s.

[fastexcel](https://github.com/ToucanToco/fastexcel) (Rust, calamine) reads xlsx, xlsm, xls, xlsb
and ods into Arrow tables with column types in 0.08 s for the same file. Its wheel is 12 MB with
no required dependencies. Arrow tables also let DuckDB run commands on Excel input through the
Arrow bridge (`refactor-duckdb-first-execution`, task 6). This is item 14 of the October 2026
engine review (`analysis/2026-10-28-undatum-engines-and-competitors.md`).

## What Changes
- **BREAKING (Excel values):** `fastexcel` becomes a base dependency, and undatum reads local
  xlsx, xlsm, xls, xlsb and ods files with it, in both engines:
  - numbers are numbers: integers when every value of the column is whole (Excel stores only
    floating-point numbers);
  - dates are dates when every value of the column is at midnight, else datetimes;
  - booleans are booleans;
  - empty cells are null;
  - formula cells give their cached results;
  - a column without a header is named `__UNNAMED__<n>`.
- **One Arrow table, two engines.** The sheet is one normalized Arrow table:
  - `RowSource.arrow_reader()` hands it to DuckDB;
  - the Python engine's reader (`undatum.io.excel.ExcelIterable`, opened by
    `s3_iterable.open_iterable` and by the Python `convert` path) yields its rows.
  - So both engines give the same records.
- **Sheets and options:** `--sheet`/`--table` (name) and `--start-page` (index) select the sheet,
  and `--start-line` skips rows before the header. Sheet names are listed with fastexcel.
- **`analyze`** reads Excel sheets through the same tables.
- **Unchanged:** compressed workbooks (`.xlsx.gz`) and cloud URIs downloaded to a temporary file
  keep working. Compressed ones are read by iterabledata as before. Writing xlsx is unchanged.

## Impact
- Affected specs: `data-processing`.
- Affected code: `pyproject.toml`, `undatum/io/excel.py` (new), `undatum/io/source.py`,
  `undatum/common/{s3_iterable,command_utils,format_names}.py`,
  `undatum/cmds/{converter,analyzer}.py`, tests and documentation.
- Users who parse Excel output that was all text (`"None"`, `"1"`, `"2021-05-06 00:00:00"`) get
  typed values instead.
