# Change: Write Every Supported Output Format from Transform Commands

## Why
Thirteen commands (`rename`, `fill`, `replace`, `enum`, `head`, `tail`, `reverse`, `search`,
`explode`, `join`, `cat`, `fixlengths`, `transpose`) write their result through `DataWriter`
(`undatum/common/iterable.py:49-115`), which only knows `csv`, `json`, `jsonl` and `bson`. With
`--output result.parquet` (or `.xlsx`, `.tsv`) they create a 0-byte file and exit with code 0 —
silent data loss in scripts and pipelines. Separately, the `data-processing` spec scenarios use a
positional output path that the CLI does not accept (the docs warn "A trailing path is not a
positional argument").

## What Changes
- File outputs of transform commands are written through `open_iterable(path, mode="w")`, so every
  writable iterabledata format and compression-by-extension works. `DataWriter` remains only for
  stdout.
- An output format that cannot be written raises `FormatError` (exit 1) and leaves no empty file
  behind.
- CSV/TSV headers are built from the union of record keys (not only the first record).
- Add a contract test matrix: each command with `--output` × {csv, tsv, jsonl, json, parquet,
  csv.gz}; the output is read back and its row count compared with the expected count. XLSX is
  read-only in iterabledata, so `--output x.xlsx` must fail with exit code 1 and no file.
- Related defects found while fixing:
  - DuckDB `COPY … (FORMAT JSON)` writes JSON Lines into `.json` files; `.json` now uses
    `ARRAY true`, and COPY paths are escaped and written atomically;
  - `DataWriter` writes the CSV header on every call, so the external-merge `sort` repeated the
    header before each row;
  - `uniq` and `frequency` opened the output file and never closed it, and wrote nothing for
    non-text formats;
  - iterabledata ignores the `delimiter` option when writing CSV, so `.tsv` output was
    comma-separated (worked around by constructing the CSV writer directly; to be fixed upstream).
- Correct the `data-processing` scenarios to the `--output` form actually accepted by the CLI.

## Impact
- Affected specs: `data-processing`
- Affected code: `undatum/common/iterable.py`, the 13 command modules in `undatum/cmds/`,
  `tests/test_output_contract.py` (new)
- Related: review defect #1
