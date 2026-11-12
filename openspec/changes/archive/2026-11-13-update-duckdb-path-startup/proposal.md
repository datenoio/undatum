# Change: Commands on the DuckDB Path Start Without iterabledata, pandas or pyarrow

## Why
`refactor-duckdb-first-execution` moved most commands on CSV, JSON and Parquet to DuckDB, but many
still import the Python engine's libraries before DuckDB runs. On a two-line CSV (macOS arm64,
Python 3.11), `count` takes 0.23 s while `frequency`, `uniq`, `sort`, `convert` and `headers` take
0.75–1.1 s, and `stats`, `schema` and `analyze` take 1.4–1.5 s. The extra time is imports:
- iterabledata's package (0.2–0.3 s), through module-level imports in `common/s3_iterable.py`,
  `common/db_source.py`, `cmds/converter.py` and `cmds/schemer.py`.
- Every iterabledata format, with pyarrow, numpy and openpyxl (0.3–0.5 s), when `detect_engine()`,
  `get_file_type()` or `constants.SUPPORTED_FILE_TYPES` look up a `.csv` file in iterabledata's
  registry, or when `convert` probes write capabilities.
- pandas (0.55–0.7 s), through module-level imports in `common/schema_utils.py`, `cmds/schemer.py`
  and `cmds/analyzer.py`.

On small and medium files this is most of a command's run time: `frequency` on 100k CSV rows
takes 0.8 s, of which 0.55 s is imports. This is item 18 of the October 2026 engine review
(`analysis/2026-10-28-undatum-engines-and-competitors.md`).

## What Changes
- **Lazy imports.** `open_iterable` in `s3_iterable` and `db_source` becomes a wrapper that imports
  iterabledata when it opens a file. pandas, qddate and openpyxl are imported in the functions
  that use them.
- **Fast format detection.** Common extensions (`format_names.FAST_FORMATS`, `FAST_CODECS`) are
  recognised without iterabledata in `detect_engine()`, `get_file_type()`, `schema`, `analyze`,
  `stats` and convert's output checks; other names still use iterabledata's detection.
- **No Python reads on the DuckDB path.**
  - `headers` takes a CSV file's fields from its header line.
  - `stats` reads its CSV type sample through DuckDB, with the values the Python reader gives
    (`COALESCE(column, '')`, one thread).
  - The DuckDB `convert` path returns a `CopyResult` with the fields of iterabledata's
    `ConversionResult`.
- **Guard.** `tests/test_startup_imports.py` runs 20 command and input combinations on the
  DuckDB path and fails when any of them imports iterabledata, pyarrow, pandas, openpyxl or
  polars.

## Impact
- Affected specs: `cli-conventions` (extends the Startup Time Budget of
  `update-cli-startup-and-logging`).
- Affected code: `undatum/common/{s3_iterable,db_source,engine_selector,schema_utils,duckdb_config,field_types}.py`,
  `undatum/utils.py`, `undatum/cmds/{converter,schemer,analyzer,selector}.py`,
  `undatum/cmds/statistics/{__init__,duckdb_engine}.py`.
- Behaviour:
  - `headers` on a CSV file with a header line and no records lists the header, where it
    printed nothing.
  - `stats` reads its CSV type sample with `--delimiter` and the other reader options; it
    ignored them before.
  - Commands that read through the Python engine (`tail`, `cat`, `diff`, `sniff`, `table`,
    `fmt`, default `dedup` and `reverse`) still import iterabledata. `analyze` imports it to
    detect the encoding.
