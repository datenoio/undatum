## 1. Compiler
- [x] 1.1 `undatum/validate/sql.py`: rules to one query with the Python messages and order;
      `None` for rules it cannot compile
- [x] 1.2 Python number grammar, NaN in ranges, values only Python reads; pattern translation
      to RE2

## 2. Wiring
- [x] 2.1 `validate --rules` and `quality --rules` use it for CSV/TSV; `validate --engine`

## 3. Verification
- [x] 3.1 Tests: the same violations as the Python rules for every check, unique and
      references, filters, fallbacks
- [x] 3.2 Benchmark, documentation and changelog
