## 1. Reader
- [x] 1.1 `undatum/io/excel.py`: sheet names, a normalized Arrow table per sheet (whole numbers as
      integers, midnight timestamps as dates), and an iterabledata-compatible reader
- [x] 1.2 `fastexcel` base dependency with bounds; `uv.lock`

## 2. Wiring
- [x] 2.1 `s3_iterable.open_iterable` and the Python `convert` path open Excel with it
- [x] 2.2 `RowSource`: Excel names recognised without iterabledata, sheet options honoured, Arrow
      reader for DuckDB
- [x] 2.3 Sheet names listed with fastexcel; `analyze` reads sheets through the tables

## 3. Verification
- [x] 3.1 Tests: typed values, sheet selection, both engines agree across commands, xls fixture,
      compressed workbook fallback
- [x] 3.2 Benchmarks, documentation and changelog
