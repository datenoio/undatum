# Change: Offline DuckDB Extensions and Non-UTF-8 CSV in DuckDB

## Why
DuckDB downloads an extension the first time a query needs it. On machines without network
access, or in containers that should not download code at run time, the only way is to install
extensions on a connected machine, copy `~/.duckdb/extensions` and set
`UNDATUM_DUCKDB_EXTENSION_DIR` (documented in installation.md). No command does this.

The extensions undatum can use are large:

| Extension | For | osx_arm64 | linux_arm64 |
|---|---|---|---|
| `encodings` | CSV text in encodings other than UTF-8 | 117 MB | 276 MB |
| `spatial` | geospatial formats and functions | 77 MB | 94 MB |
| `httpfs` | HTTP(S) and S3 URLs | 19 MB | 25 MB |
| `excel` | Excel workbooks | 11 MB | 14 MB |

None of them is used yet. CSV in Windows-1251, KOI8-R, Latin-1 and other encodings goes to the
Python engine (`refactor-duckdb-first-execution`, task 1.3), even though DuckDB's `encodings`
extension reads it. This is item 13 of the October 2026 engine review
(`analysis/2026-10-28-undatum-engines-and-competitors.md`).

## What Changes
- **`undatum extensions list`** shows each extension undatum uses, what it is for, and whether
  and where it is installed (`--json`: `undatum.extensions/1`).
- **`undatum extensions install [NAME...]`** downloads them (all four by default) into
  `--dir`, `UNDATUM_DUCKDB_EXTENSION_DIR` or DuckDB's default directory. `--force` downloads
  again.
- **No downloads at run time.** undatum checks that an extension file is present in the
  extension directory before it uses the extension. A missing extension means the Python
  engine, or an error that names `undatum extensions install <name>`.
- **Non-UTF-8 CSV in DuckDB.** When the `encodings` extension is installed, CSV and TSV text
  in another encoding is read by DuckDB instead of the Python engine.
  - The encoding is `--encoding`, or the one the Python reader detects (UTF-8 when the sample
    decodes, else chardet). The header is read in that encoding.
  - The line ending is passed explicitly: with `encodings`, DuckDB's line-ending detection
    leaves a `\n` at the start of the next row of a file with LF line ends.
  - Encodings that do not write `\r`, `\n`, `"`, `,`, `;`, `|` and tab as ASCII (UTF-16,
    UTF-32), and encodings DuckDB does not know, stay on the Python engine.
- **Docker.** The `-full` image installs the four extensions into `/opt/duckdb-extensions`
  and sets `UNDATUM_DUCKDB_EXTENSION_DIR` (about 410 MB more on Linux: `encodings` alone is
  276 MB there). The base image and the
  PyInstaller binaries do not include them; their users run `undatum extensions install`.

## Impact
- Affected specs: `distribution`, `data-processing`.
- Affected code: `undatum/common/duckdb_extensions.py` (new), `undatum/cli/extensions_cli.py`
  (new), `undatum/core.py`, `undatum/common/{command_utils,duckdb_config,engine_selector,results}.py`,
  `undatum/io/source.py`, `Dockerfile`, documentation.
- Behaviour: on a machine with the `encodings` extension installed, commands on non-UTF-8 CSV
  run in DuckDB, with the records of the Python engine.
