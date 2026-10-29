# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/datenoio/undatum/compare/v1.9.1...HEAD)

Upgrading: Python 3.11 or newer is required, and undatum now uses DuckDB 2.0. On Python 3.10 pip keeps installing 1.9.x.

### Breaking

- **Python 3.11 is the minimum version.** Python 3.10 reached end of life in October 2026; the current DuckDB, pandas, pyarrow and Polars releases need 3.11 as well.
- **DuckDB 2.0** — `duckdb>=2.0,<3` (the 2.0 LTS line, supported until October 2027; the 1.5 line ends on 2027-03-01). Queries that return one row now read their result to the end, as DuckDB 2.0 requires before the next query on a connection, and streamed results use `execute()` instead of relations, which no longer have `fetchone()`/`fetchmany()`. The `lakehouse` extra still installs, but pyducklake has no release for DuckDB 2.0 yet, so pip picks pyducklake 1.0.12, the newest one that accepts it.
- **pandas is an optional extra** — `pip install undatum` no longer installs pandas (about 70 MB with its dependencies; the base install is 249 MB instead of 318 MB). `undatum[pandas]` adds it for `Dataset.to_pandas()` and `analyze --use-pandas`, and `undatum[extract]` and `undatum[all]` include it. Without it these exit with code 2 and the `pip install` command. `analyze` and `schema --flatten-nested` describe the records undatum reads itself through an Arrow table instead of a DataFrame: integers with missing values stay integers and nested objects are structures, where a pandas frame gave `DOUBLE` and `MAP(VARCHAR, VARCHAR)`. `db query --format-out parquet` writes Parquet with pyarrow.
- **Spreadsheets are read with fastexcel, with typed values** — xlsx, xlsm, xls, xlsb and ods files are read by fastexcel (a new base dependency, 12 MB) for both engines, about 4× faster (100k rows: `convert` to Parquet 0.36 s instead of 1.9 s, `count` 0.44 s instead of 1.6 s), and DuckDB runs commands on them through Arrow. Values are typed: numbers (integers when a column holds only whole numbers), dates or datetimes, booleans, and null for empty cells. The previous reader turned every cell into text, with `"None"` for empty cells and the formula text for formula cells; formula cells now give their cached results, and a column without a header is named `__UNNAMED__<n>` instead of being dropped. `analyze` counts the records of a sheet without its header row.

### Added

- **`undatum extensions install` and `undatum extensions list`** — download the DuckDB extensions undatum uses (`encodings`, `excel`, `httpfs`, `spatial`) into a directory, for machines without network access, and show which are installed (`--json`: `undatum.extensions/1`). Commands never download an extension while they run: they use one only when it is installed in `UNDATUM_DUCKDB_EXTENSION_DIR` or DuckDB's default directory. The `-full` container image includes the four extensions (about 410 MB on Linux).
- **Non-UTF-8 CSV in DuckDB** — with the `encodings` extension installed, CSV and TSV in Windows-1251, KOI8-R, Latin-1 and other encodings are read by DuckDB in the encoding the Python engine uses (`--encoding`, or the detected one), with the same records; without it they stay on the Python engine.
- **`Dataset.to_arrow()`** — the records as a `pyarrow.Table`, or tables of `chunksize` rows. `to_pandas()` and `to_polars()` build their frames from Arrow instead of a list of records: on 1M CSV rows `to_pandas()` takes 0.9 s instead of 20.9 s, and `to_polars()` 0.6 s. A plan DuckDB runs is read straight into Arrow; other plans convert their records in batches of 10,000, and a batch whose fields mix value types Arrow cannot hold in one column becomes a frame of Python objects (`to_arrow()` raises). In pandas, list values are NumPy arrays, as in `pandas.read_parquet()`.
- **DuckDB reads ORC and Arrow/Feather inputs** — `convert`, `sort`, `uniq`, `frequency`, `select` and the row operations (`rename`, `fill`, `dedup`, `head`, ...) scan ORC and Arrow IPC/Feather v2 files through pyarrow in DuckDB instead of the Python reader, with the same records: on 1M ORC rows `sort` to CSV takes 1.0 s instead of 8.3 s, `rename` to Parquet 0.6 s instead of 4.6 s, `convert` to Parquet 1.0 s instead of 4.2 s and `frequency` 0.8 s instead of 1.8 s. Peak memory grows with the ORC stripe size (about 400–470 MB instead of 130–300 MB for row commands on 1M rows; `sort` takes up to 1 GB, as DuckDB sorts do on other inputs). Excel, Avro and Feather v1 files keep the Python reader.
- **Offline DuckDB extensions** — `UNDATUM_DUCKDB_EXTENSION_DIR` points DuckDB at preinstalled extensions on machines without network access; a command that needs a missing extension stops with exit code 2 and names it.
- **`--duckdb-threads`, `--duckdb-memory` and `--duckdb-temp-dir` on every DuckDB-backed command** — `stats`, `count`, `uniq`, `analyze`, `schema`, `quality` and `schema-drift` gain the options. These commands used DuckDB's process-wide default connection and ignored limits, the temporary directory and `UNDATUM_DUCKDB_EXTENSION_DIR`; every command now opens its own connection with the same settings. Row-wise transforms keep one thread and 256 MB by default; aggregations, sorts and profiling use every core and DuckDB's memory limit.

### Changed

- **Faster start on the DuckDB path** — commands that run in DuckDB no longer import iterabledata, pyarrow or pandas, which took 0.5-1.2 s per run. On a small CSV file `frequency`, `uniq`, `sort`, `convert` and `headers` take 0.25 s instead of 0.75-1.1 s, `stats` and `schema` 0.35 s instead of 1.4-1.5 s, and `analyze` 0.6 s instead of 1.5 s. Common file extensions are recognised without iterabledata's format detection. `headers` reads a CSV file's fields from its header line, so a file with a header and no records lists its header instead of nothing; `stats` reads its CSV type sample through DuckDB and now applies `--delimiter` and the other reader options to it. A test checks that 20 commands on the DuckDB path import none of these libraries.
- **SDK analysis methods run in DuckDB** — `Dataset.count()`, `head()`, `uniq()`, `frequency()` and `schema()` run the plan as one DuckDB query, as `write()` did, when DuckDB reads the source and every step has a SQL form, with the results of the Python engine (checked value for value by contract tests): on 1M CSV rows `count()` takes 0.2 s instead of 10.2 s, `uniq()` and `frequency()` 0.2 s instead of 8 s, and `filter(query=...).count()` 0.07 s instead of 55 s. `count()` without steps is `undatum count`. JSON values stay on the Python reader, since DuckDB types them (only `count()` and `write()` use DuckDB), and so do CSV files whose header DuckDB reads otherwise (a byte-order mark, repeated or padded names). `Dataset.read(path, engine="python")` turns DuckDB off; `write()` now also reads ORC and Arrow/Feather inputs through DuckDB.
- **Faster record output** — records are converted for JSON once instead of twice, with a fast path for records of plain values: `rename`, `fill` and other row operations writing JSON Lines take about 35% less time on 1M rows (5.9 s to 3.8 s). `uniq` and `frequency` stream DuckDB results instead of loading them all (110–170 MB less memory for 1M distinct values). Results with date columns are written to CSV and Parquet by DuckDB `COPY`, and with timestamp and time columns to Parquet (`rename` of 1M Parquet rows to Parquet: 29.5 s to 0.6 s; to CSV: 6.0 s to 0.5 s); the types `COPY` writes differently are listed and tested in one place, shared with `convert`. CSV files written by DuckDB end lines in CRLF, so they are byte-identical to the Python engine's.
- **One set of type rules for `schema`, `analyze`, `stats`, `quality` and `schema-drift`** — a CSV column gets the first of integer, number, boolean, date and datetime that at least 95% of its non-empty values convert to (placeholders such as `n/a` count as empty; `007` stays a string), and JSON and Parquet fields keep their own types. Reported types change where the commands disagreed: `schema` no longer takes the DuckDB sniffer's guess for CSV (a column with a few text values is an integer); `schema-drift` uses 95% instead of 100%, so a few bad values are not a type change; `stats` reports numbers mixing integers and decimals as `float` instead of `str`, `true`/`false` as `bool`, timestamps as `datetime` instead of `date`, and typed Parquet columns correctly; `quality` and `schema-drift` read day-first dates (`31.12.2020`) as dates and JSON strings such as `"2005"` as strings. Dates written in words are strings everywhere (only `stats` read them as dates).
- **`stats` reads the input a few times instead of four times per field** — counts, missing values, lengths and numeric distributions of all fields come from one DuckDB query; value dictionaries are grouped four fields per scan, and exact distinct counts of the other fields are packed into scans of bounded memory. The statistics are unchanged. On 100,000 rows of 61 columns `stats` takes 4 s instead of 10 s; on 2M rows of 9 columns 5.7 s instead of 7.6 s.
- **`convert` between CSV/TSV, JSON, JSON Lines and Parquet runs in DuckDB** — one `COPY` on one thread writes the output (plain, gzip or zstd) with the records of the Python engine, checked by contract tests: CSV values stay text and empty CSV fields stay empty strings. On 2M CSV rows conversion to JSON Lines takes 2 s instead of 7.5 s; Parquet output needs 300 MB instead of 800 MB on 1M rows. JSON Lines written by DuckDB are compact (no space after `:` and `,`), and `.json` output is a JSON array. Inputs with timestamps, intervals, decimals, 32-bit floats, UUIDs or binary values (and booleans, times or nested values for CSV output) keep the Python engine for text output, and inputs with UUIDs, intervals or times with a zone for Parquet output; `--engine duckdb` converts them in DuckDB anyway. CSV written by DuckDB ends lines in CRLF, as the Python writer does. The DuckDB path returns the same conversion summary.

### Fixed

- **`convert`, `flatten`, `split`, `apply` and `validate` detect the input encoding** — their `--encoding` defaulted to `utf8`, so a Windows-1251 CSV failed with "'utf-8' codec can't decode" unless `--encoding cp1251` was given; like the other commands they now detect it when the option is omitted.
- **Empty CSV fields on the DuckDB engine** — `head`, `select`, `sort`, `dedup`, `uniq`, `frequency`, `join` and the other commands DuckDB runs read empty CSV fields as missing values: JSON output had `null` where the Python engine writes `""`, `sort` put empty values last instead of first, and `join` dropped the records whose key was empty. Empty fields are now empty strings, as in the Python engine, and CSV files written by DuckDB leave them unquoted (DuckDB wrote `""`). `stats` still counts empty fields as missing values.
- **CSV with `\r\r\n` line endings on the DuckDB engine** — DuckDB left the `\n` at the start of the next row (`"\n2"` instead of `"2"`); reads now end lines as the Python engine does (`\n`, `\r\n`, `\r` and `\r\r\n`).
- **`uniq` and `frequency` on the DuckDB engine** listed values in no fixed order (`uniq`) and values with the same count in no fixed order (`frequency`). They now keep the order in which values first appear, as the Python engine and the SDK do. The query runs on one thread unless `--duckdb-threads` is given: on 1M rows it takes about 0.1 s longer and 25-30% less memory (`frequency` of a 1M-value field: 450 MB to 337 MB).
- **CSV headers on the DuckDB engine** — DuckDB's CSV sniffer took a later line for the header when a row had more values than the header (`count` reported 1 record instead of 2, `convert` wrote fields `column0`, `column1`, ...), named a numeric header `column0`, `column1`, and trimmed padded names. Every DuckDB read of CSV and TSV, including the structure `schema`, `analyze`, `stats` and `doc` read, now takes the names from the first line as the Python engine does, and values beyond the header are dropped. Headers DuckDB cannot use (empty names, names that differ only by case) are read by the Python engine. `--quotechar` now applies to DuckDB reads as well.
- **`uniq` and `frequency` with the Python engine** wrote missing values as the text `None`; they are empty CSV fields and JSON `null`, as with DuckDB.
- **`select` without `--where`** ran its own DuckDB code, which wrote timestamps to CSV with `COPY` (text different from the Python engine's) and filtered typed columns differently; it runs the `select` operation, as with `--where`.
- **DuckDB read expressions** — `uniq`, `frequency`, `sample`, `join` and `convert` built their DuckDB `read_csv` expressions without escaping the path or applying `--delimiter`; they now share one escaped builder, and `join` quotes key names with spaces or quotes.
- **`convert --engine duckdb`** wrote `null` for empty CSV fields in JSON and Parquet output, wrote `.json` files as JSON Lines, and wrote the output in place instead of atomically.
- Forward and backward fill now accept `0`, `0.0` and `False` as fallback values when no neighbour value exists.
- `undatum mcp tools --parity` (and `undatum.tools.generated.parity_report()`) no longer fails with `No module named 'click'` on an install without the `api` extra. typer 0.26 and later vendor click, so `click` is not a dependency of undatum.
- **No silent row loss on the DuckDB engine** — CSV files that are not UTF-8 (for example Windows-1251) are read by the Python engine with their detected encoding; `head`, `sort`, `select` and other commands printed nothing or only the header, and `stats` reported `count: 0`, all with exit code 0. DuckDB no longer skips rows it cannot read (`ignore_errors`): the command falls back to the Python engine, or, when records have already gone to standard output, stops with an error that suggests `--engine python`. `stats` on JSON or JSON Lines with a malformed record now fails like `head` and `count` instead of leaving the record out of the statistics.
- **`stats` on text columns** — date detection skips values that cannot be dates (hashes, e-mail addresses, codes, text over 50 characters) and gives up on a field after 20 non-date values instead of 1,000. Columns of hashes, addresses or sentences with numbers took about 100 seconds regardless of file size; a 2-million-row file now takes about 7 seconds.
- **`uniq` with the Python engine** runs in linear time; 200,000 distinct values took 99 seconds and now take about a second.
- **`dedup` and `reverse` honour `--engine`** — the option was accepted but ignored. With `--engine duckdb`, CSV, JSON and Parquet inputs are processed in DuckDB with the same records as the Python engine (2M rows: `dedup` 1.6 s instead of 10.6 s, `reverse` 2 s instead of about 30 s); the default stays on the Python engine, whose memory does not grow with the input. The performance guide no longer lists `dedup` among the commands that use DuckDB automatically.
- **Parse error hints** show command-line options (`--delimiter`, `--encoding`, `--on-error`, `--format-in`) instead of iterabledata's Python calls, and point to `undatum sniff` for the encoding instead of suggesting UTF-8 again.

## [1.9.1](https://github.com/datenoio/undatum/compare/v1.9.0...v1.9.1) - 2026-10-15

This is the first GitHub/PyPI release of the 1.9 series and includes all features and fixes listed under 1.9.0 below. The 1.9.0 release workflow stopped at its Windows verification gate before GitHub/PyPI publication.

### Fixed

- **Windows paths** — absolute drive paths, drive-relative paths, UNC shares and extended-length paths are recognized as local files rather than remote URIs. This restores commands such as `repack` with an absolute Windows input or output path.

## [1.9.0](https://github.com/datenoio/undatum/compare/v1.8.0...v1.9.0) - 2026-10-15

GitHub/PyPI publication did not complete; use 1.9.1 or later.

Upgrading: `repack` now verifies every candidate before publication and keeps the original when optimization does not save space. Use `--allow-grow` if a script requires replacement regardless of size. Replacing an existing SQLite destination requires `--sqlite-offline`; see the [repack reference](https://datenoio.github.io/undatum/commands/repack) for supported profiles and limits.

### Added

- **SQLite repack** — compact offline SQLite databases with `VACUUM INTO`, independently verify schema/settings, rowids and typed values, then publish atomically. Existing destinations require `--sqlite-offline`; active WAL/SHM/journal files and unsupported profiles are refused. Retains application metadata, AUTOINCREMENT, `WITHOUT ROWID` keys, encoding and closed WAL mode, with no new package dependency.

- **DuckDB repack** — compact offline DuckDB databases using filerepack's native database-copy algorithm, with independent catalog/typed-value verification and atomic publication. Supports measured dry-run, savings controls and native worker limits; rejects pending WALs and unsupported database objects. Initial supported profile is limited to 256 MiB input, 1 million rows and 256 MiB of decoded values per verification side.

- **Repack controls** — `--profile fast|balanced|max`, measured `--dry-run`, `--min-savings`, `--json` (`undatum.repack/1`), `--output/-o`, independent Parquet batch/row-group sizing and zstd codec threads. Decoded-byte, candidate-size, native worker RSS and timeout limits abort without publication; RSS supervision uses the optional `undatum[repack]` extra. A reproducible benchmark compares size, encoding/verification time, RSS, scratch and read-back with prior undatum and filerepack.

### Changed

- **Repack** — every destination is staged and independently verified before publication. Optimization keeps a larger/equal candidate out by default (`--allow-grow` restores always-replace); unchanged originals are copied to explicit compatible outputs. Codec/suffix conflicts, unsafe links and unsupported archive/level combinations fail before writing. Use a distinct output with a matching suffix for outer-codec changes; ORC uses compression strategies and rejects explicit `--level`.
- **Benchmarks** — the 1M-row benchmark no longer runs every night; start it from the Actions tab (Benchmarks → Run workflow) when needed. Pull requests still compare 100k-row runs with the base branch.

### Fixed

- **Repack preservation** — explicit identical input/output paths no longer truncate the input; empty Parquet remains valid. Native ORC retains typed rows, metadata and timestamp nanoseconds; native Avro retains encoded union branches, original schema/metadata/sync instead of coercing records to strings. Failed encoding or verification preserves existing destinations and source permissions/mtime/xattrs.
- **Linux repack memory limits** — worker peak RSS is measured for its own address space, avoiding false budget failures inherited from a large parent process. SQLite candidates whose runtime renumbers hidden rowids are refused without replacing existing files.
- **ORC dependency compatibility** — require pyorc 0.11 or newer after reproducing native crashes with older pyorc wheels loaded alongside PyArrow 16 on macOS; the supported lower-bound combination passes the preservation suite.
- **Data API authentication** — resources whose names begin with `docs` require the API key; only the exact documentation routes are public.
- **Partitioned output** — null and empty keys share one writer, literal null markers and composite keys cannot overwrite other partitions, and unsafe field names or symlinks cannot direct writes outside the output directory. Underscores in flat partition values are percent-encoded to distinguish keys from separators and numbered parts.
- **Quality reports** — schema comparisons use actual inferred types, and type conformance checks native values too; fractional numbers no longer pass an integer contract through rounding.
- **SDK analysis and spill** — quality, stats and packages read transformed plans with their materialized JSONL settings; reverse and backward fill preserve dates, decimals, binary and nested types when spilling to disk.
- **CLI pipelines** — CSV/TSV stdout preserves the first batch's fields and reports later additional fields instead of silently dropping them; compressed stdin keeps its codec with `--format-in`; attached and repeated format options such as `-Ojsonl` follow the command parser.
- **Agent tools and sorting** — `head` and `tail` apply the requested operation limit when returning or writing records, including zero; Python CLI sorting uses the SDK's null-safe ordering for missing and mixed values, including external merge sort.
- **Release artifacts** — the GitHub release job downloads only distributions and platform binaries, preventing unrelated build artifacts from breaking publication.
- **Release packaging** — standalone binaries dispatch supervised repack workers through their frozen entry point, with a smoke test on each platform; container builds include third-party license notices.
- **Documentation dependencies** — update image-size, fast-uri, proxy-addr and brace-expansion in the documentation build.

## [1.8.0](https://github.com/datenoio/undatum/compare/v1.7.0...v1.8.0) - 2026-10-09

Upgrading: read **Breaking** below and the [migration guide](https://datenoio.github.io/undatum/getting-started/migrating-to-2); `undatum migrate-script` rewrites deprecated commands and options in scripts.

### Breaking

- **Python 3.10 is the minimum version.** Python 3.9 reached end of life in October 2025, and 1.7.0 could not be imported on 3.9 anyway. pip on 3.9 resolves to 1.6.0
- **Errors never exit with 0.** `sample` without `--limit`/`--percent`, a misspelled `cat --mode`, an unknown `validate --rule`, and `split`/`uniq`/`frequency` on unsupported input now exit with 1; an unknown `--engine` value is a usage error (2); Ctrl-C exits with 130. `--engine iterable` keeps working as an alias of `python`
- **Records on stdout keep the input's text format** — `head`, `tail`, `sort`, `sample`, `search`, `dedup` and the other record commands print CSV for CSV input (TSV for TSV, JSON for JSON) instead of always JSON Lines; binary or unknown inputs still print JSON Lines. Add `-O jsonl` (`--format-out jsonl`) for the previous output
- **`--delimiter` describes the input only and is auto-detected when omitted** — 36 commands defaulted it to `,`, which misread TSV and `;`-separated files; `convert x.tsv y.csv` no longer copies the input delimiter into the output
- **JSON documents carry a `schema` id** — `stats -O json` drops `"version": 1.0` for `"schema": "undatum.stats/1"`; `headers -O json` lists fields in file order and adds `schema` and `file`; `formats list --json` is an object (`{"schema": ..., "formats": [...]}`) instead of an array; `sniff` reports `delimiter: null` (was `"N/A"`) and the compression codec as `compression` (it was wrongly reported as `encoding`); `diff -O json` prints only the JSON document on stdout (the summary line goes to stderr)
- **Unknown names in validation rule files are errors** — a misspelled `format:`, `custom:` or `type:` (for example `format: emial`) stops the run with exit code 2 and the closest name, instead of being skipped with a warning; violations in `validate --json` use `rule` and `row` (were `rule_name` and `record_index`)
- **`split` rewritten** — parts are written in the input's format (or `--format-out`) instead of always JSON Lines for field splits, every input format is supported, and splitting a CSV by `--fields` works (it wrote nothing before); field-split file names percent-encode special characters and use `__null__` for empty values
- **`transpose` output** — one record per input field: `field` plus `row_0`, `row_1`, ... (fields in file order); the extra first record that spread field names across the `row_N` columns is gone
- **SDK `Dataset` is lazy** — transform methods return a new plan and read nothing; the plan runs on iteration, `write()`, `count()`, `stats()` and other terminal methods. Chains no longer write a temporary file per step, and values keep their Python types between steps. `Dataset.close()` is now a no-op, and the private `_source` attribute is replaced by the `source` property
- **`--autodoc` masks samples sent to remote AI providers** — `analyze`, `doc` and `package create` replace values in columns that look like personal data (`email`, `phone`, `ssn`, ...) with `***` before a data sample goes to a remote provider. `--no-pii-mask-samples`, `UNDATUM_AI_PII_MASK_SAMPLES=false` or `pii_mask_samples: false` in `undatum.yaml` turns this off; samples for local providers (`ollama`, `lmstudio`) are unchanged unless `--pii-mask-samples` is given
- **Data API key only in the `X-API-Key` header** — `?api_key=` is ignored (keys no longer end up in access logs); keys are compared in constant time
- **Elasticsearch ingestion verifies TLS certificates** — use `--ca-cert` for private CAs or `--insecure` to opt out. There is no default ingest pipeline any more (was `ent-search-generic-ingestion`); pass `--es-pipeline` if you need one. `ingest --timeout` defaults to the driver default instead of `-30`
- **Elasticsearch driver is an extra** — install `undatum[elastic]` for `db load` into Elasticsearch/OpenSearch and `elasticsearch://` sources; `undatum[all]` installs every extra. `pymongo` stays in the base install because it provides the `bson` module for BSON files

### Added

- **SQL expressions** — `--where "amount > 100 AND city = 'Berlin'"` on `select`, `search`, `head`, `sample`, `count` and `convert`, and repeatable `--add "total = price * qty"` on `select` and `convert`. DuckDB evaluates them on typed values (text columns get the number, date or boolean type most of their values have) while the output keeps the original text; inputs DuckDB cannot read are evaluated in batches with the same results. Unknown columns are reported with suggestions; subqueries, table functions and `getenv` are refused. Also available as the `where` agent tool
- **Partitioned output** — `convert data.csv out/ --partition-by year,month -O parquet` and `split --fields region --hive` write Hive-style `field=value/` directories readable by DuckDB, Spark, Athena and BigQuery, in any writable format (DuckDB `COPY ... PARTITION_BY` for CSV/Parquet with DuckDB 1.5 or later, a streaming writer otherwise). `--max-open-files` (default 128) bounds open files, so high-cardinality keys work
- **Schema drift detection** — `diff --schema OLD NEW` (also `undatum schema diff`) reports added, removed, retyped and nullability-changed fields and likely renames (similar name or shared values); `schema-drift FILES... [--baseline schema.json]` (also `undatum schema drift`) checks a set of deliveries against a baseline data file, `undatum schema --json` output, JSON Schema or Frictionless schema. `--fail-on added,removed,type,nullability,any` exits with 1 for CI; text, Markdown and JSON reports
- **Validation rule library** — rule files can use `format: date` (with `formats`), `datetime`, `phone` (E.164; national numbers with `region` and `undatum[phone]`), `country`, `currency`, `language` (ISO code lists bundled), `iban`, `uuid`, `pattern`, `integer`, `number`, `boolean`, plus `unique: true` and `references: {file, field}` (values must exist in another file); `undatum validate --list-rules` prints the catalogue and `-O jsonl` writes one violation per line. Violations in JSON have the keys `rule`, `field`, `severity`, `row`, `value`, `message`
- **`undatum quality`** — one report per dataset: per-field empty values, distinct and top values, type and type conformance; differences from an expected schema (`--schema`); rule violations by severity (`--rules`); and a pass/fail verdict from a thresholds file (`min_rows`, `max_null_rate`, `min_type_conformance`, `max_error_violations`, `schema: strict|additive`). Markdown, standalone HTML or JSON (`undatum.quality/1`); exits with 1 when a threshold fails, for CI. Also `Dataset.quality()` and `command: quality` in pipelines
- **JSON output for informational commands** — `--json` (same as `--format-out json`) on `count`, `headers`, `sniff`, `stats`, `schema`, `diff`, `validate`, `analyze`, `formats list` and `config show` prints one JSON document with a versioned layout id (`"schema": "undatum.count/1"`). Layouts are documented on the [JSON output](https://datenoio.github.io/undatum/commands/json-output) page and published as JSON Schema files. In JSON mode errors are a JSON object on stderr (`{"error": {"code": "file_not_found", ...}}`) with the usual exit codes. Agent tools `count_records`, `list_fields`, `sniff_file` and `diff_files` return the same documents
- **Unix pipelines** — `-` as the input path reads standard input (format and `.gz`/`.zst`/`.bz2`/`.xz` compression detected from the first bytes, `--format-in` to override), e.g. `cat data.csv | undatum sort - --by a | undatum head - -n 3`. Record commands accept `--format-out`/`-O` for stdout; binary formats are refused on a terminal. Closing the pipe early (`| head -1`) exits with 0
- **`db load` into ClickHouse and SQL Server** — `clickhouse://` (batched inserts with `clickhouse-connect`, `--create-table` with inferred `Nullable` types and `--table-engine`, append and replace) and `mssql://` (pyodbc with `fast_executemany`, `--create-table`, append, replace and `MERGE`-based upsert); integration tests run against service containers in CI
- **`db load` into MongoDB and Elasticsearch/OpenSearch** — `--db mongodb://host/db` (collection = `--table`) and `--db elasticsearch://host:9200` / `opensearch://` (HTTPS; `+http` for plain HTTP; index = `--table`) with `--api-key`/`ELASTIC_API_KEY`, `--doc-id`, `--ca-cert`, `--insecure`, `--es-pipeline`, so the deprecated `ingest` is no longer needed
- **Database steps in pipelines** — `command: db load` (also `db query`, `db dump`) replaces the deprecated `ingest` step
- **GCS and Azure cloud connectors** — first-class `gs://`/`gcs://` and `az://`/`abfs://`/`abfss://` URIs next to S3 for CLI, SDK, TUI/web, and Data API resources; extras `undatum[gcs]` and `undatum[azure]`; missing-extra errors name the install command
- **SDK methods** — `Dataset.from_records()`, `replace()`, `exclude()`, `concat()`, `limit()`, `slice()`, `fixlengths()`, `transpose()`, `collect()`, `explain()`, `uniq()`, `frequency()`, `validate()` and `schema()`; `write()` runs the plan as one DuckDB query when every step has a SQL form
- **Agent tools for every operation** — MCP and LangChain get one tool per operation of the registry (`dedup`, `join`, `rename`, `sort`, ...), with JSON Schemas generated from the operation configs; results come back inline, or are written to `output_path` with `confirm=true`. `undatum mcp tools --parity` lists which CLI commands have a tool. LangChain tools now publish their argument schemas
- **MCP resources and prompts** — the MCP server lists the data files under its root (`undatum://datasets`), and serves each file's schema and sample (`undatum://dataset/{path}/schema`, `.../sample`) and the format catalogue (`undatum://formats`); prompts `profile-dataset`, `draft-validation-rules`, `plan-conversion` and `document-dataset` give clients ready plans. The server runs on mcp 1.x (`FastMCP`) and 2.x (`MCPServer`); paths stay inside the sandbox root
- **`undatum migrate-script`** rewrites deprecated commands and options (`--filetype`, `--outtype`, `--n`, `--engine iterable`, `profile`, `document`, `scheme`) in shell scripts, Makefiles, Markdown and pipeline YAML to the current names; it shows a diff, `--write` applies it and `--check` fails CI while anything is left. A [migration guide](https://datenoio.github.io/undatum/getting-started/migrating-to-2) lists every change, including `ingest` → `db load`
- **`migrate-script` opt-out markers** — text that shows old spellings on purpose stays as it is: `<!-- migrate-script: ignore -->` (or `# migrate-script: ignore` in scripts and YAML) on a line of its own skips the next table, paragraph or fenced code block, at the end of a line it skips that line, and `ignore-start` / `ignore-end` skip a range. Marked lines are neither rewritten nor reported, so `undatum migrate-script --check docs/docs` passes on the migration guide and the `ingest` page. `scheme FILE` now becomes `schema FILE --format cerberus` (the file argument stays first, also after a redirection or pipe), and `--stype` on a continuation line no longer leaves a second `--format`
- **Container image and packaging** — a `Dockerfile` (slim, non-root, `undatum` entrypoint; `--build-arg EXTRAS=full` for the common extras); release tags build, smoke-test and publish `ghcr.io/datenoio/undatum:<version>` and `:<version>-full` before PyPI publishing, and pull requests that touch the image build it. A Homebrew formula template with a release job (runs once a tap repository is configured) and a conda-forge recipe (waits for iterabledata on conda-forge) are in `packaging/`
- **Performance benchmarks** — `scripts/benchmarks.py` measures wall time and peak memory of 18 commands on generated 100k- and 1M-row CSV/JSON Lines/Parquet files, with per-command budgets in `tests/benchmarks/budgets.toml` (`make bench`). Pull requests are compared with the base branch on the same runner and fail on a regression above 20%; a nightly 1M-row run keeps a history chart on the documentation site
- **Documentation site** — user docs live in `docs/` (Docusaurus, content in `docs/docs/`) and are published at https://datenoio.github.io/undatum/: getting started, cookbook, use cases, CLI reference, formats, integrations and development pages. New pages cover the shared CLI options (`--flatten-nested`, `--on-error`, `--error-log`, `--table`/`--sheet`, `--quotechar`, `--filter`), the pipeline YAML reference, MCP client configuration (Cursor, Claude Desktop) and a tool catalogue
- **Generated reference** — every command page ends with a reference generated from the CLI (capabilities: formats read and written, memory use, engines; usage, arguments, options with types and defaults, deprecated spellings); the [Python SDK reference](https://datenoio.github.io/undatum/integrations/sdk-reference), the validation rule catalogue and the JSON Schema files of the JSON layouts are generated too. CI fails when any of them is stale
- **Executable documentation** — every shell example in the docs runs in CI against fixture files (`scripts/run_doc_examples.py`); examples that need a server, cloud storage or an AI provider are marked `norun`
- **Development docs** — architecture, testing, benchmarks and releasing pages replace `openwiki/`; `AGENTS.md` is a short guide with links
- **`undatum[dev]` extra** — pinned ruff and mypy, pytest, pytest-cov, pytest-benchmark, pre-commit (`make install-dev` uses it)

### Changed

- **One option vocabulary** — `--format-in`, `--format-out`, `--output`, `--limit`, `--fields`, `--delimiter`, `--engine` everywhere, with short flags `-F`, `-O`, `-o`, `-n`, `-f`, `-d`, `-e`, and `--filter` on every command that filters (`select`, `validate`, `split`, `flatten`, `apply` as on `frequency`, `uniq`, `plot`; `--filter-expr` stays an alias). `--engine` accepts only `auto`, `duckdb`, `python` (`iterable` is an alias)
- **Quiet by default** — no INFO log lines on stderr; global `-v` / `-vv` / `-q`; progress bars go to stderr and only in a terminal
- **Fast start** — commands import their dependencies on use; `undatum --help` takes ~0.15 s instead of ~0.8 s
- **Streaming transforms** — `rename`, `fill`, `replace`, `search`, `head`, `tail`, `slice`, `enum`, `explode`, `exclude`, `fixlengths`, `fmt`, `cat`, `dedup`, `join` and `mask` no longer hold the dataset in memory: on 1M rows `rename` peaks at about 150 MB (was 800 MB) and memory no longer grows with the input. `reverse` and `fill --strategy backward` spill to disk; `transpose` holds one column at a time. CI checks the budget (300 MB for 1M rows)
- **DuckDB pushdown** — `rename`, `fill`, `replace`, `search`, `head` and `slice` run as one DuckDB query on CSV/TSV/JSON/JSON Lines/Parquet inputs (7x faster for `rename` on 1M CSV rows) and produce the same records as the Python engine (checked by contract tests); `--engine` is available on these commands
- **Faster commands on CSV/TSV/JSON/Parquet** — iterabledata (about 1 s to import, as it loads every format and database driver) is imported only when a command reads through it; DuckDB-backed runs skip it, so `undatum head data.csv` takes 0.7 s instead of 2.1 s
- **Commands that write `.csv`, `.json`, `.jsonl` or `.parquet` through DuckDB** no longer import iterabledata to look up the output format: `rename` and `fill` on 100k rows take 0.25 s and 86 MB (were 3 s and 165 MB); `count` takes 0.19 s on 500k rows (was 0.53 s) and uses the row count stored in ORC, Arrow and DBF files
- **Faster `stats` on text columns** — date detection caches repeated values, skips values without digits and stops checking a column after 1,000 values unless at least half were dates: 15.5 s → 2.5 s on 100k rows with hash and free-text columns, with the same types reported
- **`s3://` reads stream** through s3fs when it is installed (`undatum[cloud]`) instead of downloading the object first
- **One AI stack** — `--autodoc` on `analyze`, `schema`, `schema-bulk`, `doc` and `package create` uses iterabledata's providers, like `undatum ai`: `anthropic`, `gemini`, `azure` and `openai-compatible` now work there too (they disabled autodoc before), `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` select a provider when none is configured, and `--ai-model` also applies to field descriptions. Configuration names are unchanged
- **New `undatum.io` and `undatum.ops` packages** — typed (dataclass) operations with Python and SQL implementations, and one source/sink layer, shared by the CLI, the SDK and the agent tools
- **CLI code layout** — the data commands moved from one 3,800-line `undatum/cli/data_commands.py` to `undatum/cli/commands/` (one module per area: `convert`, `explore`, `describe`, `records`, `fields`, `combine`, `quality`, `query`), with shared option aliases in `undatum/cli/options.py`
- **Plugin commands** can be registered lazily through the `undatum.commands` entry point group
- **Exit codes** are documented in the troubleshooting page and `man undatum` (0, 1, 2, 3, 4, 130)
- **Version** is defined only in `undatum/__init__.py`
- **GitHub repository** moved from `datacoon/undatum` to [`datenoio/undatum`](https://github.com/datenoio/undatum). GitHub redirects the old URLs; documentation is at https://datenoio.github.io/undatum/
- **CI runs on `master`** (it was configured for `main` and never ran) with lint, tests on 3.10–3.13, base install without extras, clean-wheel smoke, lowest-dependency, deprecation, dependency audit, type check, memory budget, documentation build and examples, and database integration jobs; coverage must stay at or above 65%
- **Release pipeline** — tests, clean install, binaries and the container image must pass before anything is published; `rc` tags go to TestPyPI; distributions and binaries carry build provenance attestations; release notes come from Conventional Commits via git-cliff (`cliff.toml`); binaries are also built on pull requests that touch `packaging/`
- **Tooling** — `ruff format` replaces black and pylint is dropped; tool versions are pinned once in the `dev` extra and checked against pre-commit and CI (`scripts/check_tool_versions.py`); `uv.lock` pins CI and binary builds
- **Dependencies** — every runtime dependency and extra has lower and upper bounds, checked in CI, and the lower bounds are tested on Python 3.10 (`lowest direct dependencies` job, now blocking). Direct dependencies on `tqdm`, `tabulate`, `chardet`, `xlwt`, `jsonlines`, `numpy`, `zipp` and `dnspython` were removed: progress bars and report tables use `rich`, encoding detection uses iterabledata. The base install is 62 packages (was 70). typer 0.26 or later is required: older typer releases with click 8.5 drop the argument descriptions from `--help`
- **Lint and types** — ruff also applies pylint (`PL`) rules and, for `undatum/cmds/` and `undatum/sdk/`, Google docstring (`D`) rules; mypy runs as a blocking ratchet (`mypy-baseline.json`, errors per file may only go down) with `undatum/common/` fully annotated
- **Repository** — `SECURITY.md`, issue and pull request templates, `CODEOWNERS`, and a workflow that auto-merges passing Dependabot patch updates (needs "Allow auto-merge" in the repository settings)

### Deprecated

Everything below keeps working (commands and options print a warning) and is removed in 2.0; `undatum migrate-script` rewrites it.

- **Commands** `profile`, `document`, `ingest` and `scheme` (use `stats`, `doc`, `db load`, `schema --format cerberus`); they no longer appear in `--help`. The `ingest` pipeline step is deprecated too (use `command: db load`)
- **Option spellings** `--filetype` (use `--format-in`), `--outtype` and `--output-format` (`--format-out`), `--format` where it selects the output serialization (`--format-out`), `--n` and `--objects-limit` (`--limit`)

### Removed

- **`undatum.common.iterable`** (`DataWriter`, `BSONWriter`) — write records with `undatum.common.writer` (`write_records`, `emit_records`, `StdoutSink`)
- **`undatum/cli/data_commands.py`** — the commands live in `undatum/cli/commands/`
- **Legacy AI provider classes** — `undatum.ai.OpenAIProvider`, `OpenRouterProvider`, `OllamaProvider`, `LMStudioProvider`, `PerplexityProvider`, the abstract `undatum.ai.base.AIService`, and the modules `undatum.ai.providers`, `undatum.ai.perplexity` and `undatum.ai.schemas`. Use `undatum.ai.get_ai_service()`, which returns an `AIService` dataclass over `iterable.ai`
- **Legacy configuration** — `tox.ini`, `setup.cfg`, `flake8`, `requirements.txt` and `.coveragerc`; everything lives in `pyproject.toml`
- **`openwiki/`** — replaced by the development pages of the documentation site

### Fixed

- **Clean install** — `pip install undatum` (or pipx/uv) crashed on `undatum --version` with `No module named 'starlette'`; optional extras are imported only when their command runs, and missing extras exit with 2 and an install hint
- **`--output` in any writable format** — `rename`, `fill`, `replace`, `enum`, `head`, `tail`, `reverse`, `search`, `explode`, `join`, `cat`, `fixlengths`, `transpose`, `uniq`, `frequency` and `fmt` wrote an empty file with exit code 0 for Parquet, TSV and other non-CSV/JSON formats. Outputs are now written to a temporary file and renamed on success; a format that cannot be written (for example `.xlsx`) fails before anything is created
- **`--format-in`** was only used to pick the engine and never reached the reader, so files with an unusual extension (`data.txt -F csv`) or a compressed container without a format suffix (`data.zip -F jsonl`) could not be read; compressed files read with an explicit format (`x.csv.gz -F csv`) also lost their codec
- **Compressed CSV with another delimiter** (`data.csv.gz` separated by `;`) was read with `,`: delimiter detection read the compressed bytes. `.gz`, `.bz2`, `.xz`, `.zst` and `.zip` are now decompressed for detection, and the Python reader uses the detected delimiter too
- **CSV fields with doubled quotes** (`"say ""hi"""`) were read as `say ""hi""` by every DuckDB path (`select`, `stats`, `sort`, ...)
- **`.json` output from DuckDB paths** (`sort`, `dedup`, `slice`, `join`, `select`) was JSON Lines; it is now a JSON array. Output paths in `COPY` are escaped
- **`select` and `sort` (external merge)** printed JSON Lines on stdout regardless of the input format
- **`sort --engine python`** repeated the CSV header before every row; **`.tsv` output** was comma-separated
- **`sort` and `count` with the DuckDB engine** failed on paths containing `'` and (`sort`) on field names with spaces or quotes, and fell back to the slower Python engine with a warning; they now use the shared reader, so doubled quotes in CSV fields and `--format-in` work there too
- **`sample`/`search` with the DuckDB engine** always fell back to the Python engine (and then failed on a leftover log statement)
- **`dedup` with the DuckDB engine** did not keep the first record of each key and reordered the output; deduplication now keeps first-appearance order on every input, and nested values (lists, objects) no longer crash the all-fields key
- **`convert --threads N`** always fell back to sequential processing because `open_path()` rejected the `engine` argument
- **Empty Parquet, ORC and Feather outputs** were 0-byte files that readers reject
- **`mask` without `--output`** failed instead of printing the masked records
- **`headers`** lists fields in file order instead of an arbitrary order
- **`sniff`** reported the compression codec as the encoding, never detected the delimiter, and always said `has_header: false`; it now detects encoding, delimiter and header, and counts records with the fast `count` path
- **`schema`** no longer prints a warning about the "iterable engine" on every run; a failed `schema --format` conversion is reported instead of silently printing the default format
- **`schema-bulk`** exits non-zero when some files fail, and `--output DIR` no longer fails when the directory does not exist
- **`validate --fields/--rule`** printed statistics as `b'...'`, ignored `--mode valid`, and read only CSV/JSONL/BSON; it now reads every supported format
- **`validate` format rules** crashed when a format had an entry in the rule map without a function
- **Errors in validation rule files** (unknown rule type, malformed file) exit with 1 instead of 4; Python's own `FileNotFoundError` from deep inside a reader exits with 1 instead of 4
- **Missing optional dependencies** exit with 2 and say which package to install (they were reported as internal errors with 4); `db query`/`db load`/`db dump` no longer turn database and dependency errors into exit code 1
- **`db load` reported success when rows failed** — failed batches were logged and the command exited with 0; it now loads the remaining batches and exits with 3, naming the first failure. The Elasticsearch integration test ran without its client in CI and was skipped
- **Elasticsearch** — the client was created with `timeout=`, which elasticsearch-py 8/9 rejects; ingestion without `--doc-id` rejected every document (the ID field defaults to `id` as documented)
- **PostgreSQL/MySQL URIs** without credentials crashed with `UnboundLocalError`; percent-encoded passwords are decoded
- **`undatum[mcp]`** failed with `mcp` 2.x, which removed the `FastMCP` API the MCP server used
- **`undatum[clickhouse]`** installed `clickhouse-driver`; `clickhouse://` sources need `clickhouse-connect`
- **ZSTD files** — `zstandard` (needed by iterabledata for `.zst`) is now a core dependency
- **`--autodoc` with an unreachable AI provider** stopped `analyze` with an internal error (exit 4) after minutes of retries; a local provider (Ollama, LM Studio) that is not listening is now detected in 2 seconds, and a failing provider skips the AI content with one warning. AI errors that do surface exit with 3
- **Data API** — every route used the pagination limits of the last configured resource; queries now run outside the event loop with a timeout (`--query-timeout`, HTTP 504)
- **SDK** — chained operations left a full temporary JSONL copy per step; temporary files are removed on `close()`, garbage collection or exit, and `Dataset` is a context manager
- **`pipeline templates init`** failed in scripts and CI because it prompted for variables without a terminal; it now uses the template defaults and `--var` values
- **`undatum web`** imports python-multipart under its current module name (`python_multipart`) and only falls back to the deprecated `multipart`
- **TUI and web UI** suggested the deprecated `undatum profile`; they show `undatum stats`
- **Release binaries** — PyInstaller now freezes a wrapper entry point, `undatum/__main__.py` uses package-relative imports, and `packaging/undatum.spec` is no longer gitignored, so tagged builds find it
- **Documentation examples** match the CLI: `ai plan` takes two positional paths, `ai filter` takes the expression before the file, write examples use `--output`, and the `schema-bulk`, `convert --flatten-data` and `replace --global-replace` spellings and the Data API authentication notes are corrected; edit links point to `master`

## [1.7.0](https://github.com/datenoio/undatum/compare/v1.6.0...v1.7.0) - 2026-08-13

### Added

- `**--flatten-nested**` on inspect and file transforms (`analyze`, `select`, `head`, `tail`, `table`, `uniq`, `frequency`, `headers`, `sort`, `sample`, `search`, `dedup`, `fill`, `rename`, `mask`, `plot`, `validate`, `sniff`, `split`, `join`, `diff`, `exclude`, `tui`, `web`, `ingest` / `db load`, `doc`, `package create` / `add-resource`, and the other single-file row commands) — unfold nested dict / array-of-dict fields onto dotted paths (`--max-nested-depth` and `--keep-nested-parents` / `--no-keep-nested-parents`; keep-parents default on). SDK `Dataset.read(..., flatten_nested=True)` applies the same projection when iterating; agent tools (`frequency`, `deduplicate`, `mask_fields`, `sample_data`) accept `flatten_nested`
- `**Dataset.convert_many**` — SDK bulk convert (`to_ext`, `filename_pattern`; same as `convert --recursive`)
- `**defaults.quotechar**` / `UNDATUM_QUOTECHAR` — default CSV quote character (same config path as `delimiter`)
- `**--error-log PATH**` — append iterabledata parse errors as JSONL (use with `--on-error skip` or `warn`)
- `**ai filter --flatten-nested**` — unfold nested fields into dotted paths for schema context and `--apply`; `--max-nested-depth` and `--keep-nested-parents` / `--no-keep-nested-parents` pass through when flattening
- `**ai filter --sample-size**` — rows sampled when inferring schema context for a file (engine default 10000 when omitted)
- `**schema --validate --sample-size**` — rows sampled when inferring the schema used for validation (engine default 10000 when omitted)
- `**ai suggest --sample-size**` — override how many sample rows are sent to the suggestion engine (default 5 when omitted)
- `**--quotechar**` — CSV quote character on convert, inspect, transforms, `split`, `ingest` / `db load`, `package`, `tui`, `web`, `plot`, `ai filter`, and `ai suggest` (iterabledata default `"`)
- `**convert --row-group-size**` — Parquet write row-group size (iterabledata `row_group_size`; defaults to the writer batch size when omitted; skips DuckDB COPY)
- `**convert --level**` — explicit codec compression level (iterabledata `codecargs.compression_level`; overrides `--profile`; skips DuckDB COPY)
- `**convert --filename-pattern**` — bulk output names with `{name}`, `{stem}`, `{ext}` (used with `--recursive`)
- `**convert --batch-size**` on native batch — forwarded as iterabledata `BatchSelection.batch_size` (Parquet/Arrow scanner chunks)
- `**ai doc --job-id**` — stable job identifier for documentation progress and JSON results (engine generates one when omitted)
- `**ai doc --sample-size` / `--detect-constraints` / `--statistics` / `--temperature` / `--max-tokens**` — pass-throughs into iterabledata documentation generation (`--no-detect-constraints` and `--no-statistics` disable the defaults; temperature and max tokens are omitted so engine defaults apply)
- `**ai doc --progress**` — print iterabledata documentation stages to stderr
- `**formats describe**` — show read/write memory, selection pushdown, codecs, source constraints, flat/tabular, native bulk I/O, and example iterableargs from the catalog
- `**--on-error raise|skip|warn**` — iterabledata parse-error policy on convert, inspect, file transforms, `split`, `tui`, `web`, `ingest` / `db load`, `package`, and `ai filter` / `ai suggest`; DuckDB paths skip to iterable when `skip` or `warn` is set
- `**--table` / `--sheet**` on convert, inspect, file transforms, `split`, `tui`, and `web`; two-file commands also take `--table2`; `ingest` / `db load` use `--source-table`; `package create` / `add-resource`, `ai filter`, and `ai suggest` take `--table`; agent tools (`frequency`, `deduplicate`, `mask_fields`, `sample_data`) accept `table`; SDK methods inherit `table=` from `Dataset.read()`
- `**ai doc --context**` — JSON prompt context; `--include-field-descriptions` and `--validate-output` on the non-block generate path
- `**schema --validate**` — check rows against an inferred schema (`--strict` flags fields not present in that schema); keep `undatum validate` for rule packs
- `**ai doc` default blocks** now include `agent_skill` and `codebook`
- `**convert --use-totals**` — use format-reported row totals for progress when available
- **SDK** — `Dataset.read(..., table=)` iterates the named sheet/table; `Dataset.stats(flatten_nested=True)` unfolds nested fields
- `**undatum formats tables SOURCE**` — list named sheets/tables before convert
- `**ai suggest --apply**` — apply a suggested transform spec (confirm unless `--yes`)
- `**ai doc --tables` / `--cache` / `--pii-mask-samples**` — pass-throughs into iterabledata documentation generation
- `**convert --write-mode**` — lakehouse append / overwrite / error / ignore / create
- `**--trust**` — acknowledge pickle deserialization risk on convert, stats, schema, select, and head
- `**formats list --capabilities**` — maturity, native bulk read/write, and extra columns
- **Native batch convert** — `--native-batch`, `--columns`, `--row-range START:END`; auto-enabled with `--low-memory` when both formats advertise native bulk I/O
- `**--profile fast|balanced|max**` on `convert` — codec performance profiles for compressed output (same profiles as `repack`)
- `**--keep-nested-parents**` on `stats` (default on) and `schema` (default off) — with `--flatten-nested`, keep parent dict/array fields alongside dotted children
- `**--max-nested-depth**` on `stats` and `schema` — with `--flatten-nested`, cap unfold depth (engine default 5)
- `**--flatten-nested**` on `stats` and `schema` — unfold nested dict / array-of-dict fields onto dotted paths
- **iterabledata extras as undatum extras** — `undatum[lakehouse]`, `[gis]`, `[scientific]`, `[access]`, `[compression]`
- `**undatum web**` — optional local browser session (`pip install "undatum[web]"`) over the same sampled processors as the TUI; default bind `127.0.0.1:8765`; HTMX-boosted forms; one action at a time; not a spreadsheet and not the read-only Data API
- `**undatum tui**` — optional Textual explorer (`pip install "undatum[tui]"`) that previews a bounded sample (default 200 rows); profile (`s`), frequency (`f`), sample filter (`/`), export (`e`), SQL (`ctrl+s`, default LIMIT 500), command palette (`:`), convert/save-as (`w`), validate sample (`v`), mask preview (`m`), pipeline YAML (`p`), and `s3://` open from the file picker (`u`); not a spreadsheet editor
- **Data API hardening** — optional `--api-key` / `UNDATUM_API_KEY`, `--cors-origins`, `s3://` resource paths, and JSON Schema validation for API configs
- `**stats --format-out json**` — machine-readable profiling output (also used when `--output` ends in `.json`)
- `**stats` HTML/Markdown reports** — `--format-out html|markdown` (also inferred from `.html` / `.md` output paths)
- **Plugin I/O and transforms** — connector plugins on the iterable path, `undatum apply --plugin`, and `undatum plugins validate`
- **Schema for Excel/XML/DOCX** — `schema` uses analyzer-style extraction for xlsx/xls/xml/docx
- **SDK result objects** — `Dataset.stats()` returns `StatsResult`; `head`/`tail` return `QueryResult`
- **Single-binary release artifacts** — PyInstaller linux/mac/win builds and smoke tests on tagged releases
- `**plot --filter` / `--aggregate**` — filter records before plotting; bar charts support `count`/`sum`/`mean` with `--value-field` and `--top-n`
- `**frequency` / `uniq --filter**` — DuckDB `WHERE` pushdown when the expression translates to SQL; otherwise the same comparison subset is evaluated in-process
- **JSON analysis output** — `headers`, `frequency`, and `uniq` accept `--format-out json` (also inferred from a `.json` output path); `sniff` accepts `--format-out json` / `.json` output
- **CLI defaults config** — `defaults:` in `undatum.yaml` or `~/.undatum/config.yaml` (and `UNDATUM_*` env vars) set engine, threads, progress, encoding, delimiter, and format_out; inspect with `undatum config show`
- **`undatum(1)` man page** — generated from the CLI (`make man`); installed to `share/man/man1`
- **`analyze --format-out`** — JSON/YAML/Markdown also inferred from `.json` / `.yaml` / `.md` output paths; omitted `--engine` no longer disables DuckDB
- **`pipeline doc`** — Mermaid flowchart (Markdown by default) from a pipeline YAML/JSON spec
- Pipeline validation accepts current commands (`sql`, `plot`, `repack`, `profile`, …) by reading the live CLI (`tui` and `web` are excluded)
- **`jsonl-normalization` pipeline template** and example connector/transform plugins
- Dependabot config for pip security patches and GitHub Actions updates
- **`--threads` process-pool parallelism** — opt-in chunk parallelism for Python-engine `convert`, `validate`, `stats`, and `frequency` (GitHub #18); ordered output; DuckDB paths stay single-process

### Changed

- `**iterabledata>=1.0.18**` is now a floor dependency so convert/stats/schema can use codec profiles, nested flatten, and the current format catalog
- `**--filter**` evaluates comparison/boolean expressions (`==`, `AND`/`OR` or `&&`/`||`) in-process with no MistQL; unsupported syntax (`LIKE`, `IN`, `match`) errors and points to `undatum sql`

### Removed

- `**undatum query**` and the `**mistql**` dependency — use `undatum sql` for DuckDB SQL over files, or `select --filter` for comparison filters (`undatum db query` is unchanged)

### Fixed

- `**pipeline run**` executes steps in-process (Typer argv mapping) instead of treating
`registered_commands` as a dict; `input`/`output` map to positionals for `convert`/`count`/`sql`,
`keys` maps to `--key-fields`, temp outputs are only injected for commands that accept an output
path, and later steps can use `$step_name` or the previous step's output
- Raised minimum dependency versions to address historical Snyk advisories for `setuptools`,
`dnspython`, `numpy`, and `zipp`.

## [1.6.0](https://github.com/datenoio/undatum/compare/v1.5.0...v1.6.0) - 2026-07-22

### Added

- `**repack` command** — recompress container codecs (`.gz`/`.zst`/…) at max by default, or rewrite Parquet/ORC/AVRO with native compression; supports `--level` and `--progress`
- `**--low-memory` on convert/sort/dedup** — spill-to-disk paths for large files (DuckDB COPY for duckable→Parquet converts; external merge sort; disk-backed exact dedup)
- `**db dump**` — export a table or SQL query to Parquet/CSV/JSONL
- **CI install-gate** — clean-venv wheel install smoke for convert/stats across Python versions
- `**pyarrow**` as a default dependency so Parquet works out of the box
- Quote-aware CSV delimiter sniffing via `csv.Sniffer` over multi-line samples
- Excel `--start-page` support on `uniq`, `frequency`, and `select`
- Docs: format support matrix, task quickstarts, tool positioning, uv/pipx install paths
- `**package add-resource` and `package validate` subcommands** — extend existing packages and validate descriptors (full validation with optional `undatum[frictionless]`)
- `**Dataset.package()` SDK method** — programmatic Frictionless Data Package generation
- **Pipeline `package` step** — direct Packager integration for `create`, `add-resource`, and `validate`
- `**undatum[frictionless]` optional extra** — installs `frictionless` for full package validation
- `**ai doc` schema enrichment** — SDMX-style field-name hints, LLM field-name remapping to canonical columns, and BOM-stripped JSONL keys for block-based schema documentation
- **CSV delimiter auto-detection** — semicolon, tab, and pipe delimiters detected automatically when `--delimiter` is omitted (analyze, convert, select, doc, package, and shared read paths)

### Changed

- `**DUCKABLE_CODECS**` accepts iterabledata's `"gz"` id (and `"gzip"`) so gzipped files route to DuckDB
- Repo hygiene: removed committed `pylint_report.txt`, `data.csv`, and IDE dirs; fixed CHANGELOG placeholder dates
- `**package create**` — emits Frictionless profile/resource metadata, inferred coverage fields, schema uniqueness constraints, wired read options (`delimiter`, `encoding`, `tagname`, etc.), single-pass `--autodoc`, Rich success output, portable relative resource paths, and optional `--zip` archive output
- **Shared schema type mapping** — Frictionless/JSON Schema conversions centralized in `schema_utils`
- `**analyze**` — DuckDB-accelerated tabular analysis, per-field uniqueness statistics, S3 URI support, and improved nested JSON/XML table handling
- `**ai doc**` — uses block-based schema generation with post-enrichment; preserves the original source filename in output
- `**select**` — DuckDB `COPY` fast path for CSV/JSON/Parquet output; dot-notation nested field selection; filter expressions pushed to SQL when translatable
- `**filter` SQL translation** — comparison and boolean expressions translate to DuckDB `WHERE` clauses for accelerated filtering
- `**convert**` — removed legacy format-specific converters; routes through iterabledata with shared delimiter resolution
- **Shared `command_utils`** — centralized iterable read options, CSV delimiter resolution, and DuckDB read expressions
- **Docs synced with iterabledata 1.0.14–1.0.18** — format matrix and README now cover Avro writes, codec profiles (`fast`/`balanced`/`max`), GeoJSON Text Sequence / TAR / genomic VCF, Zarr / FlatGeobuf / genomic-interval / OTLP profiles, experimental open-data GIS/scientific/business formats, Paimon and DuckLake, and Delta/Iceberg write support (via `iterabledata[lakehouse]` and related extras). Catalog described as 140+ formats; `formats list --capabilities` remains authoritative for the installed engine

### Fixed

- `**repack` progress bar** — closing an indeterminate tqdm bar (`total=None`) no longer raises `TypeError: bool() undefined…`
- `**package create**` — uses `UndatumError` hierarchy for missing inputs/files; avoids duplicate LLM calls when `--autodoc` is enabled
- `**analyze**` — handles empty record sets without failing schema inference
- `**uniq**` — DuckDB engine keeps results instead of reporting an unsupported engine

### Notes

- **iterabledata engine upgrades** (inherited when `pip` resolves a recent iterabledata on Python 3.10+; undatum still declares `requires-python >= 3.9`):
  - **1.0.14** — Avro write support; ORC schema inference for unusual column names; DuckDB/SQLite default table names from output filename
  - **1.0.16** — `geojsonseq`, read-only `tar` multi-member containers, `genomic_vcf`; XXE-hardened XML; stricter parse-error policy on some formats
  - **1.0.17** — codec performance profiles; native Parquet/Arrow batch conversion; Zarr, GeoParquet, FlatGeobuf, BED/GFF, CRAM, OTLP profiles; bounded columnar I/O
  - **1.0.18** — experimental open-data format pack (FileGDB, MIF, LAS, Access, MAT, SEG-Y, GRIB2, IATI, …); Paimon Row/Mosaic/tables and DuckLake; Delta Lake and Iceberg bounded writes (Hudi remains read-only)

## [1.5.0](https://github.com/datenoio/undatum/compare/v1.4.0...v1.5.0) - 2026-06-29

### Added

- `**api openapi` command** — export OpenAPI 3.x schema from an API config without starting the server (`--output`, `--format json|yaml`)
- **Data API discovery endpoint** — `GET /` returns resource list and documentation links
- **Data API startup banner** — prints base URL, resource endpoints, and `/docs` links when the server starts
- `**httpx**` added to the `api` optional extra (required for HTTP integration tests)

### Changed

- **Data API list responses** — endpoints now return `{data, pagination}` instead of a bare JSON array (**breaking** for API clients)
- **Data API OpenAPI** — per-resource query parameters, field schemas, and `field__op` filter documentation in Swagger UI
- **Data API sorting** — `sort=field` and `sort=-field` aliases supported alongside `order_by` / `order_dir`
- **Data API pagination** — optional `include_total=true` adds total matching row count to the response envelope
- **CI** — test job installs `undatum[api]` so Data API HTTP tests run in CI

### Fixed

- **Data API** — discover stores absolute file paths; warns on resource name collisions; validates files at serve time; skips composite primary-key detail routes; serializes DuckDB types (dates, decimals, UUIDs) to JSON-safe values
- **Data API** — `serve`, `run`, and `openapi` raise a clear `DependencyError` when the `api` extra is not installed
- `**api-serve-data` recipe** — default flow uses `api run`; config path defaults to `api-config.yml`

## [1.4.0](https://github.com/datenoio/undatum/compare/v1.3.0...v1.4.0) - 2026-06-26

### Added

- `**ai` commands** - AI-assisted workflows backed by iterabledata's `iterable.ai` stack: `ai doc` (block-based dataset documentation with metadata enrichment and PII-safe sampling), `ai filter` (natural-language/DSL to filter translation, with `--apply` to execute and stream matching rows), `ai plan` (declarative conversion planning), and `ai suggest` (transform suggestions). Supports OpenAI, Anthropic, Gemini, Azure, OpenRouter, Ollama, LM Studio, and Perplexity, defaulting to undatum's existing AI configuration
- `**formats` commands** - `formats list` surfaces iterabledata's full format catalog; `--capabilities` shows the runtime capability matrix (read/write/streaming/etc.) per format, with machine-readable JSON output
- `**mcp` commands** - `mcp serve` starts a Model Context Protocol stdio server exposing undatum's agent tools; `mcp tools` lists the available tools. New `undatum-mcp` console script
- **Agent tools (`undatum.tools`)** - 17 JSON-schema agent tools for LLM function calling: the 12 iterabledata foundation tools (detect, schema, stats, convert, validate, analyze, documentation, etc.) re-exported as the single source of truth, plus 5 undatum-specific tools (`query_sql`, `frequency`, `deduplicate`, `mask_fields`, `sample_data`). Includes OpenAI/Anthropic tool definitions, a unified `call_tool`, and a LangChain `get_tools()` adapter
- **SDK DataFrame & typed-row interop** - `Dataset.to_pandas()`, `to_polars()`, `to_dask()`, `as_dataclasses()`, and `as_pydantic()`, delegating to iterabledata's adapters
- **Bulk conversion** - `convert --recursive` (with `--to-ext`) converts a directory or glob pattern, treating OUTPUT as a directory
- **Extended database engines** - `db query` and file-reading commands now reach MS SQL Server (`mssql://`, `sqlserver://`), ClickHouse (`clickhouse://`), MongoDB (`mongodb://`), and Elasticsearch/OpenSearch (`elasticsearch://`, `opensearch://`) via iterabledata's read-only drivers; driver options can be passed through the URI query string (`?collection=`, `?index=`, `?limit=`, ...). New `undatum/common/db_source.py`
- **Cloud storage URIs beyond S3** - GCS (`gs://`/`gcs://`), Azure (`az://`/`abfs://`/`abfss://`), and `s3a://` are opened natively via iterabledata's fsspec support; `s3://` writes are now supported (delegated to iterabledata) instead of raising
- New optional extras: `mcp`, `langchain`, `polars`, `dask`, `cloud` (fsspec/s3fs/gcsfs/adlfs), `mssql` (pyodbc), `clickhouse` (clickhouse-driver)

### Changed

- `convert` now routes through iterabledata's engine, supporting any format it can read/write (100+ formats, including cloud URIs) as input or output. Read-only and schema-required output formats (protobuf, Cap'n Proto, Thrift) fail fast with actionable, capability-aware error messages and writable-format suggestions
- `SUPPORTED_FILE_TYPES`, `COMPRESSED_FILE_TYPES`, `TEXT_DATA_TYPES`, and `BINARY_FILE_TYPES` are now derived at import time from iterabledata's registries (with static fallbacks when iterabledata is unavailable), so undatum recognizes every format and codec the underlying engine supports
- `doc` command metadata extraction (keywords, geographic/temporal coverage, language, theme) and semantic-type/PII detection now delegate to `iterable.ai.metadata` and `iterable.ai.semantic` while keeping CLI output backward compatible

## [1.3.0](https://github.com/datenoio/undatum/compare/v1.1.1...v1.3.0) - 2026-06-11

### Added

- `**mask` command** - Anonymize sensitive fields with redact, deterministic hash, and randomize methods
- `**pipeline` commands** - Run and validate multi-step YAML/JSON workflows (`pipeline run`, `pipeline validate`)
- `**pipeline templates` commands** - List built-in pipeline templates and initialize pipelines from them (`pipeline templates list`, `pipeline templates init`)
- `**examples` commands** - Browse and run a built-in recipe library (`examples list`, `examples show`, `examples run`); recipes now ship inside the package
- `**plot` command** - Generate histogram, bar, scatter, and line charts with matplotlib
- `**db query` / `db load` commands** - Execute SQL against PostgreSQL/MySQL/SQLite and load files into database tables
- **Data API** - Serve files as a read-only HTTP API (`api discover`, `api serve`, `api run`) via the `api` extra
- `**package create` command** - Generate Frictionless Data Package descriptors
- `**extract` command** - Extract tables/text from PDF/DOC/DOCX/XLS/XLSX via the `extract` extra
- `**profile` command** - Alias for `stats`
- **Python SDK** - `Dataset` fluent API (`from undatum import Dataset`) with read/write, transforms, and analysis methods returning real values (`stats()`, `count()`, `head()`, `tail()`)
- **Plugin system** - Entry-point based plugins (`undatum.plugins` group) with `plugins list` / `plugins info` commands
- **Rich validation rules** - YAML/JSON rule files with severity levels for `validate`
- **Error handling framework** - `UndatumError` hierarchy with actionable messages, typo suggestions, and consistent exit codes
- **S3 support** - Read/write `s3://` URIs in major commands via the `s3` extra
- **Parallel processing infrastructure** - Chunked I/O, threading helpers, and progress bars
- New optional extras: `plot` (matplotlib), `s3` (boto3), `postgres` (psycopg2-binary), `mysql` (pymysql)
- **CI quality gates** - ruff, black, and coverage thresholds enforced in GitHub Actions; advisory mypy job; Python 3.12/3.13 added to the test matrix; `.pre-commit-config.yaml` added
- `**sql` command** - Ad-hoc DuckDB SQL queries over data files with jsonl/csv/parquet output (`undatum sql "SELECT ..." file.csv`)
- `**--version` flag** - Print the undatum version

### Changed

- `stats` (DuckDB and iterable engines) now returns a structured profile dictionary in addition to printing the profile table
- Recipes used by the `examples` command moved into the package (`undatum/recipes/`) so they work in PyPI installs
- Packaging is now fully `pyproject.toml`-based; legacy `setup.py` removed and templates/recipes declared as package data
- Removed unused direct dependency on `click`
- `core.py` split into per-domain CLI modules under `undatum/cli/` (data, pipeline, db, api, package, examples, plugins); `undatum.core` is now a thin assembly module
- Shared command scaffolding: `get_iterable_options` / `ITERABLE_OPTIONS_KEYS` centralized in `undatum/common/command_utils.py` (was duplicated in 31 modules) along with a `run_with_duckdb_fallback` helper
- Commands that previously logged an error and exited with code 0 on invalid parameters or unsupported output formats now raise `ValidationError` / `FormatError` (non-zero exit codes)
- Removed deprecated `IterableData` reader class; reading goes through `iterabledata`'s `open_iterable`. `DataWriter` is retained as the supported writer for open file objects (e.g. stdout)
- Logging configuration moved from import time (`undatum.core`) to the CLI entry point
- `ingester.py` (1,900 lines) decomposed into a package with one module per database backend (`undatum/cmds/ingester/`)
- `statistics.py` (1,200 lines) decomposed into a package with engine detection, DuckDB engine, and iterable engine modules (`undatum/cmds/statistics/`)
- S3 (`s3://`) input paths now work across all file-reading commands via a shared S3-aware opener
- `--progress` flag wired into `convert`, `validate`, and `join`
- `--threads` now configures the DuckDB engine across DuckDB-backed commands (stats, sort, dedup, search, join, select, slice, sample, sql)
- Connector plugins are now consulted in the shared I/O path: custom URI schemes (e.g. `myproto://...`) handled by an installed `ConnectorPlugin` work in all file-reading commands
- `plugins info` now lists the command names registered by command plugins

### Fixed

- DuckDB stats engine: implemented missing value, distribution, and type-category computations (previously the DuckDB path always fell back to the iterable engine)
- `Dataset` SDK methods `count()`, `head()`, `tail()` returned placeholder values; they now return actual results
- `Dataset.read()` options (encoding, delimiter, etc.) are now applied when iterating
- Unsupported database URI schemes (e.g. `http://`) now raise a clear error instead of being treated as SQLite paths
- Fixed YAML syntax error in the `api-serve-data` recipe

## [1.1.1](https://github.com/datenoio/undatum/compare/v1.1.0...v1.1.1) - 2026-01-19

### Added

- Added workflow and OpenSpec documentation for change proposals and agent workflows
- Added dataset documentation examples under `examples/doc/`

### Changed

- Expanded README with documentation pointers and dataset doc references

## [1.1.0](https://github.com/datenoio/undatum/compare/v1.0.18...v1.1.0) - 2026-01-18

### Added

- **Phase 1 Data Commands**: Added 7 new fundamental data processing commands:
  - `count` - Count rows in data files with DuckDB optimization for supported formats
  - `table` - Pretty-print data as aligned table for inspection using Rich library
  - `head` - Extract first N rows from files
  - `tail` - Extract last N rows using efficient buffering
  - `enum` - Add row numbers, UUIDs, or constant values to records
  - `reverse` - Reverse the order of rows in files
  - `fixlengths` - Normalize field counts by padding or truncating rows
- **Phase 2 Data Commands**: Added 9 new data cleaning and transformation commands:
  - `sort` - Sort rows by one or more columns with ascending/descending and numeric options
  - `sample` - Random sampling using reservoir sampling algorithm (fixed count or percentage)
  - `search` - Regex-based search and filtering across fields
  - `dedup` - Remove duplicate rows with key-field and keep-first/last options
  - `fill` - Fill empty/null values with constants or forward/backward fill strategies
  - `rename` - Rename fields by exact mapping or regex patterns
  - `explode` - Split columns by separator into multiple rows
  - `replace` - String replacement in fields with simple and regex support
  - `cat` - Concatenate files by rows (vertical) or columns (horizontal)
- **Phase 3 Data Commands**: Added 7 new advanced data processing commands:
  - `join` - Relational joins between files (inner, left, right, full outer) with hash-based and DuckDB SQL implementations
  - `diff` - Compare two files and show differences (added, removed, changed rows) with key-based comparison
  - `exclude` - Remove rows from input file where keys match exclusion file using hash lookup
  - `transpose` - Swap rows and columns with proper header handling
  - `sniff` - Detect file properties (delimiter, encoding, types, record count) with text/JSON/YAML output
  - `slice` - Extract specific rows by range or index list with DuckDB optimization
  - `fmt` - Reformat CSV data with delimiter, quote style, escape character, and line ending options
- **Schema Command Improvements**: Enhanced schema command with:
  - Full output format support (text/json/yaml) - previously ignored options now work
  - Working AI documentation with provider selection
  - Record counting included in schema output
  - Improved file format detection (XLSX, XLS, XML, DOCX)
  - Compression detection and reporting
  - Engine selection (auto/duckdb/iterable) for performance
  - Comprehensive error handling
  - Glob pattern support in bulk mode
  - Shared utilities (`schema_utils.py`) eliminating code duplication with analyzer
- **Schema Format Exports**: Added support for industry-standard schema formats:
  - `jsonschema` - JSON Schema (W3C/IETF standard) for API validation and OpenAPI specs
  - `avro` - Apache Avro schema format for Kafka message schemas and Hadoop pipelines
  - `parquet` - Parquet schema format for data lake schemas and Parquet file metadata
  - `cerberus` - Cerberus validation schema format (for backward compatibility with deprecated `scheme` command)
- **Stats Command DuckDB Optimization**: Added DuckDB engine support for statistics generation:
  - 10-100x faster statistics for CSV, JSONL, JSON, and Parquet files
  - Leverages DuckDB's `SUMMARIZE` and SQL aggregations for columnar processing
  - Automatic engine selection with fallback to iterable engine for unsupported formats
- **Database Ingestion Improvements**: Enhanced `ingest` command with:
  - MySQL support with auto-create table, upsert, and batch operations
  - SQLite support (file and in-memory) with PRAGMA optimizations, auto-create table, and upsert
  - Improved PostgreSQL, DuckDB, MongoDB, and Elasticsearch support

### Changed

- **Migrated to external iterabledata library**: All commands now use `open_iterable()` from the external `iterabledata` library instead of local `IterableData` class
- **Improved resource management**: All iterable operations now use try/finally blocks for proper resource cleanup
- **Batch write operations**: Commands now use `write_bulk()` for improved performance on large datasets
- **Iterator reset support**: Commands that need multiple passes over data now use `reset()` method when available
- **Schema command consolidation**: `scheme` command now redirects to `schema --format cerberus` with deprecation warning, unified schema interface with format selection
- **Stats command performance**: DuckDB engine provides dramatic performance improvements for supported formats

### Deprecated

- **Local IterableData class**: The `undatum.common.iterable.IterableData` class is deprecated and will be removed in a future version. Use `open_iterable()` from `iterable.helpers.detect` instead.
- **Local DataWriter class**: The `undatum.common.iterable.DataWriter` class is deprecated and will be removed in a future version. Use `open_iterable()` with `mode='w'` instead.
- `**scheme` command**: The `scheme` command is deprecated. Use `undatum schema --format cerberus` instead. The `scheme` command will show a deprecation warning but continues to work for backward compatibility.

### Fixed

- Fixed resource leaks in `statistics`, `textproc`, and `ingester` commands by properly closing iterable objects
- Fixed bug in `textproc.flatten()` where `fromfile` was used instead of `filename` parameter
- Fixed schema command output format options being ignored
- Fixed schema command AI documentation not working
- Fixed schema command missing record counting

## [1.0.18](https://github.com/datenoio/undatum/compare/v1.0.17...v1.0.18) - 2025-12-15

### Fixed

- Declared runtime dependencies in `pyproject.toml` and aligned `setup.py` so `pip install undatum` installs all required packages in clean environments

## [1.0.17](https://github.com/datenoio/undatum/compare/v1.0.16...v1.0.17) - 2025-12-12

### Changed

- **Improved CLI documentation**: Enhanced all command-line interface functions with detailed help text using Typer's `Annotated` types
- **Code refactoring**: Refactored analyzer output writing into separate `_write_analysis_output()` function for better maintainability
- **Better file handling**: Improved file output handling in analyzer command with proper context managers

### Fixed

- Fixed analyzer output not writing to files correctly when `--output` option was used
- Improved consistency between stdout and file output formatting

## [1.0.16](https://github.com/datenoio/undatum/compare/v1.0.15...v1.0.16) - 2025-12-12

### Added

- **Multi-provider AI support**: Added support for OpenAI, OpenRouter, Ollama, LM Studio, and Perplexity APIs
- **Structured AI output**: Replaced fragile text parsing with JSON Schema-based structured output for reliable AI responses
- **Flexible AI configuration**: Support for environment variables, config files (`undatum.yaml` or `~/.undatum/config.yaml`), and CLI arguments with proper precedence
- **AI provider factory**: New `get_ai_service()` function for easy provider instantiation
- **Enhanced error handling**: Proper exception classes (`AIServiceError`, `AIConfigurationError`, `AIAPIError`) with clear error messages
- **CLI arguments for AI**: Added `--ai-provider`, `--ai-model`, and `--ai-base-url` options to `analyze` command
- **Configuration management**: New `undatum/ai/config.py` module for unified configuration handling
- **Backward compatibility**: Old `get_fields_info()` and `get_description()` functions maintained for compatibility
- Enhanced code quality improvements and Pylint score improvements
- Better error handling and resource management

### Changed

- **AI system refactoring**: Completely refactored AI documentation system from Perplexity-only to multi-provider architecture
- **Structured responses**: All AI providers now use JSON Schema (`response_format: json_object`) instead of parsing CSV from markdown code blocks
- **Provider architecture**: Implemented abstract base class `AIService` with concrete provider implementations
- Improved code quality: fixed indentation, trailing whitespace, and formatting issues
- Refactored file operations to use `with` statements for better resource management
- Updated string formatting to use f-strings and lazy logging
- Fixed dangerous default arguments in function signatures
- Improved type hints and code documentation
- Updated `analyze` command to accept AI provider configuration
- Updated `schemer` command to use new AI service interface

### Fixed

- Fixed critical bug: added missing `_process_json_data` function in analyzer module
- Fixed bad indentation issues in `duckdb_decompose` function
- Fixed redefined builtin `id` parameter (renamed to `table_id`)
- Fixed unused imports and arguments
- Fixed dictionary iteration patterns (removed unnecessary `.keys()` calls)
- Fixed `isinstance()` calls to use tuple syntax for better performance
- Improved file handling with proper context managers
- **Fixed fragile AI response parsing**: Replaced error-prone text extraction with proper JSON parsing
- **Fixed AI service initialization**: Added proper error handling and fallback when AI service fails to initialize

## [1.0.15](https://github.com/datenoio/undatum/compare/v1.0.14...v1.0.15) - 2024-12-12

### Added

- Code quality improvements and linting fixes
- Better resource management with context managers
- Added `ingest` command for data ingestion
- Added globbing support for ingest command

### Changed

- Improved Pylint score from 6.30/10 to 7.60/10
- Refactored code for better maintainability
- Updated transformation (apply command) code to use iterabledata library
- Updated several commands to reuse iterabledata lib, more file formats supported by headers, frequency, stats and convert commands
- Replaced prettytables and tabulate with Rich library for better output formatting
- Updated analyze command to support automatic fields documentation generation

### Fixed

- Fixed JSON output for analyzer command
- Minor fixes and improvements

## [1.0.14](https://github.com/datenoio/undatum/compare/v1.0.13...v1.0.14) - 2024-11-20

### Added

- Added support to convert CSV and JSONL to ORC and AVRO formats
- Added parquet compression option
- Added encoding option for analyze command to allow manually set encoding
- Added formats conversion table to documentation

## [1.0.13](https://github.com/datenoio/undatum/compare/v1.0.12...v1.0.13) - 2022-04-20

### Fixed

- Fixed conversion xlsx-to-jsonl

### Added

- Added experimental command "query", not documented yet. Allows to use mistql query engine.

## [1.0.12](https://github.com/datenoio/undatum/compare/v1.0.11...v1.0.12) - 2022-01-30

### Added

- Added command "analyze" it provides human-readable information about data files: CSV, BSON, JSON lines, JSON, XML. Detects encoding, delimiters, type of files, fields with objects for JSON and XML files. Doesn't support Gzipped, ZIPped and other compressed files yet.

## [1.0.11](https://github.com/datenoio/undatum/compare/v1.0.10...v1.0.11) - 2022-01-30

### Changed

- Updated setup.py and requirements.txt to require certain versions of libs and Python 3.8

## [1.0.10](https://github.com/datenoio/undatum/compare/v1.0.9...v1.0.10) - 2022-01-29

### Added

- Added encoding and delimiter detection for commands: uniq, select, frequency and headers. Completely rewrote these functions. If options for encoding and delimiter set, they override detected. If not set, detected delimiter and encoding used.
- Added support of .parquet files to convert to. It's done in a simplest way using pandas "to_parquet" function.

## [1.0.9](https://github.com/datenoio/undatum/compare/v1.0.8...v1.0.9) - 2022-01-18

### Added

- Added support for CSV and BSON files for "stats" command

## [1.0.8](https://github.com/datenoio/undatum/compare/v1.0.7...v1.0.8) - 2021-07-14

### Changed

- Replaced json with orjson for some operations. Keep looking on performance changes and going to replace or json lib calls to orjson

## [1.0.7](https://github.com/datenoio/undatum/compare/v1.0.6...v1.0.7) - 2020-10-26

### Added

- Added initial code to convert JSON lines files to CSV

## [1.0.6](https://github.com/datenoio/undatum/tree/v1.0.6) - 2020-04-20

### Added

- First public release on PyPI and updated github code

