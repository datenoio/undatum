## 1. Extensions
- [x] 1.1 `common/duckdb_extensions.py`: the extensions undatum uses, the extension directory,
      whether one is installed (file present, no download), install
- [x] 1.2 `undatum extensions list` / `install` with `--dir`, `--force`, `--json`
      (`undatum.extensions/1`)
- [x] 1.3 `load_extension()` points to `undatum extensions install`

## 2. Non-UTF-8 CSV
- [x] 2.1 `duckdb_csv_encoding()`: UTF-8, or the Python reader's encoding when `encodings` is
      installed and DuckDB reads it with ASCII line ends, quotes and delimiters
- [x] 2.2 `duckdb_csv_text_expr()` reads the header and the text in that encoding with an
      explicit line ending; `detect_engine()` and `RowSource` use it

## 3. Distribution
- [x] 3.1 Docker `-full` image installs the extensions and sets `UNDATUM_DUCKDB_EXTENSION_DIR`

## 4. Verification
- [x] 4.1 Tests: install and list against a temporary directory, no download when an extension
      is missing, CLI parity on the Windows-1251 fixture when `encodings` is installed
- [x] 4.2 Documentation (installation, extensions command, performance) and changelog
