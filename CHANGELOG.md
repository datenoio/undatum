# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased](https://github.com/datenoio/undatum/compare/v1.7.0...HEAD)

### Breaking

- **Python 3.10 is the minimum version.** Python 3.9 reached end of life in October 2025, and 1.7.0 could not be imported on 3.9 anyway. pip on 3.9 resolves to 1.6.0.
- **Errors never exit with 0.** `sample` without `--n`/`--percent`, an unknown `--engine` value, a misspelled `cat --mode`, an unknown `validate --rule`, and `split`/`uniq`/`frequency` on unsupported input now exit with 1; Ctrl-C exits with 130. `--engine iterable` keeps working as an alias of `python`
- **Data API key only in the `X-API-Key` header** — `?api_key=` is ignored (keys no longer end up in access logs); keys are compared in constant time
- **Elasticsearch driver is an extra** — install `undatum[elastic]` for `db load` into Elasticsearch/OpenSearch and `elasticsearch://` sources; `undatum[all]` installs every extra. `pymongo` stays in the base install because it provides the `bson` module for BSON files
- **`transpose` output** — one record per input field: `field` plus `row_0`, `row_1`, ... (fields in file order); the extra first record that spread field names across the `row_N` columns is gone
- **SDK `Dataset` is lazy** — transform methods return a new plan and read nothing; the plan runs on iteration, `write()`, `count()`, `stats()` and other terminal methods. Chains no longer write a temporary file per step, and values keep their Python types between steps. `Dataset.close()` is now a no-op, and the private `_source` attribute is replaced by the `source` property
- **Records on stdout keep the input's text format** — `head`, `tail`, `sort`, `sample`, `search`, `dedup` and the other record commands print CSV for CSV input (TSV for TSV, JSON for JSON) instead of always JSON Lines; binary or unknown inputs still print JSON Lines. Add `-O jsonl` (`--format-out jsonl`) for the previous output
- **`--delimiter` describes the input only and is auto-detected when omitted** — 36 commands defaulted it to `,`, which misread TSV and `;`-separated files; `convert x.tsv y.csv` no longer copies the input delimiter into the output
- **Elasticsearch ingestion verifies TLS certificates** — use `--ca-cert` for private CAs or `--insecure` to opt out. There is no default ingest pipeline any more (was `ent-search-generic-ingestion`); pass `--es-pipeline` if you need one. `ingest --timeout` defaults to the driver default instead of `-30`
- **Unknown names in validation rule files are errors** — a misspelled `format:`, `custom:` or `type:` (for example `format: emial`) stops the run with exit code 2 and the closest name, instead of being skipped with a warning; violations in `validate --json` use `rule` and `row` (were `rule_name` and `record_index`)
- **`split` rewritten** — parts are written in the input's format (or `--format-out`) instead of always JSON Lines for field splits, every input format is supported, and splitting a CSV by `--fields` works (it wrote nothing before); field-split file names percent-encode special characters and use `__null__` for empty values
- **JSON documents carry a `schema` id** — `stats -O json` drops `"version": 1.0` for `"schema": "undatum.stats/1"`; `headers -O json` lists fields in file order and adds `schema` and `file`; `formats list --json` is an object (`{"schema": ..., "formats": [...]}`) instead of an array; `sniff` reports `delimiter: null` (was `"N/A"`) and the compression codec as `compression` (it was wrongly reported as `encoding`); `diff -O json` prints only the JSON document on stdout (the summary line goes to stderr)
- **`--autodoc` masks samples sent to remote AI providers** — `analyze`, `doc` and `package create` replace values in columns that look like personal data (`email`, `phone`, `ssn`, ...) with `***` before a data sample goes to a remote provider. `--no-pii-mask-samples`, `UNDATUM_AI_PII_MASK_SAMPLES=false` or `pii_mask_samples: false` in `undatum.yaml` turns this off; samples for local providers (`ollama`, `lmstudio`) are unchanged unless `--pii-mask-samples` is given

### Fixed

- **Clean install** — `pip install undatum` (or pipx/uv) crashed on `undatum --version` with `No module named 'starlette'`; optional extras are imported only when their command runs, and missing extras exit with 2 and an install hint
- **`--output` in any writable format** — `rename`, `fill`, `replace`, `enum`, `head`, `tail`, `reverse`, `search`, `explode`, `join`, `cat`, `fixlengths`, `transpose`, `uniq`, `frequency` and `fmt` wrote an empty file with exit code 0 for Parquet, TSV and other non-CSV/JSON formats. Outputs are now written to a temporary file and renamed on success; a format that cannot be written (for example `.xlsx`) fails before anything is created
- **`.json` output from DuckDB paths** (`sort`, `dedup`, `slice`, `join`, `select`) was JSON Lines; it is now a JSON array. Output paths in `COPY` are escaped
- **`sort --engine python`** repeated the CSV header before every row; **`.tsv` output** was comma-separated
- **`convert --threads N`** always fell back to sequential processing because `open_path()` rejected the `engine` argument
- **Data API** — every route used the pagination limits of the last configured resource; queries now run outside the event loop with a timeout (`--query-timeout`, HTTP 504)
- **Elasticsearch** — the client was created with `timeout=`, which elasticsearch-py 8/9 rejects
- **PostgreSQL/MySQL URIs** without credentials crashed with `UnboundLocalError`; percent-encoded passwords are decoded
- **SDK** — chained operations left a full temporary JSONL copy per step; temporary files are removed on `close()`, garbage collection or exit, and `Dataset` is a context manager
- **`validate --fields/--rule`** printed statistics as `b'...'`, ignored `--mode valid`, and read only CSV/JSONL/BSON; it now reads every supported format
- **`schema-bulk`** exits non-zero when some files fail; a failed `schema --format` conversion is reported instead of silently printing the default format
- **ZSTD files** — `zstandard` (needed by iterabledata for `.zst`) is now a core dependency
- **Release binaries** — PyInstaller now freezes a wrapper entry point; `undatum/__main__.py` uses package-relative imports
- **`undatum[mcp]`** failed with `mcp` 2.x, which removed the `FastMCP` API the MCP server used (the server now supports both, see Added)
- **`undatum[clickhouse]`** installed `clickhouse-driver`; `clickhouse://` sources need `clickhouse-connect`
- **Missing optional dependencies** exit with 2 and say which package to install (they were reported as internal errors with 4); `db query`/`db load`/`db dump` no longer turn database and dependency errors into exit code 1
- **`validate` format rules** crashed when a format had an entry in the rule map without a function
- **`select` and `sort` (external merge)** printed JSON Lines on stdout regardless of the input format
- **Elasticsearch ingestion without `--doc-id`** rejected every document; the ID field defaults to `id` as documented
- **`--format-in`** was only used to pick the engine and never reached the reader, so files with an unusual extension (`data.txt -F csv`) or a compressed container without a format suffix (`data.zip -F jsonl`) could not be read; compressed files read with an explicit format (`x.csv.gz -F csv`) also lost their codec
- **`mask` without `--output`** failed instead of printing the masked records
- **`pipeline templates init`** failed in scripts and CI because it prompted for variables without a terminal; it now uses the template defaults and `--var` values
- **`schema-bulk --output DIR`** failed when the directory did not exist
- **TUI and web UI** suggested the deprecated `undatum profile`; they show `undatum stats`
- **CSV fields with doubled quotes** (`"say ""hi"""`) were read as `say ""hi""` by every DuckDB path (`select`, `stats`, `sort`, ...)
- **`dedup` with the DuckDB engine** did not keep the first record of each key and reordered the output; deduplication now keeps first-appearance order on every input, and nested values (lists, objects) no longer crash the all-fields key
- **Empty Parquet, ORC and Feather outputs** were 0-byte files that readers reject
- **`headers`** lists fields in file order instead of an arbitrary order
- **`sample`/`search` with the DuckDB engine** always fell back to the Python engine (and then failed on a leftover log statement)
- **Compressed CSV with another delimiter** (`data.csv.gz` separated by `;`) was read with `,`: delimiter detection read the compressed bytes. `.gz`, `.bz2`, `.xz`, `.zst` and `.zip` are now decompressed for detection, and the Python reader uses the detected delimiter too
- **`sniff`** reported the compression codec as the encoding, never detected the delimiter, and always said `has_header: false`; it now detects encoding, delimiter and header, and counts records with the fast `count` path
- **Errors in validation rule files** (unknown rule type, malformed file) exit with 1 instead of 4; Python's own `FileNotFoundError` from deep inside a reader exits with 1 instead of 4
- **`schema`** no longer prints a warning about the "iterable engine" on every run
- **`--autodoc` with an unreachable AI provider** stopped `analyze` with an internal error (exit 4) after minutes of retries; a local provider (Ollama, LM Studio) that is not listening is now detected in 2 seconds, and a failing provider skips the AI content with one warning. AI errors that do surface exit with 3
- **`db load` reported success when rows failed** — failed batches were logged and the command exited with 0; it now loads the remaining batches and exits with 3, naming the first failure. The Elasticsearch integration test ran without its client in CI and was skipped
- **`sort` and `count` with the DuckDB engine** failed on paths containing `'` and (`sort`) on field names with spaces or quotes, and fell back to the slower Python engine with a warning; they now use the shared reader, so doubled quotes in CSV fields and `--format-in` work there too
- **`undatum web`** imports python-multipart under its current module name (`python_multipart`) and only falls back to the deprecated `multipart`

### Changed

- **One option vocabulary** — `--format-in`, `--format-out`, `--output`, `--limit`, `--fields`, `--delimiter`, `--engine` everywhere, with short flags `-F`, `-O`, `-o`, `-n`, `-f`, `-d`, `-e`. Old spellings (`--filetype`, `--outtype`, `--output-format`, `--format` for serialization, `--n`, `--objects-limit`) keep working with a deprecation warning until 2.0. `--engine` accepts only `auto`, `duckdb`, `python` (`iterable` is an alias); a typo is a usage error (exit 2)
- **Duplicate commands hidden** — `profile`, `document`, `ingest`, `scheme` no longer appear in `--help` and warn when used
- **Quiet by default** — no INFO log lines on stderr; global `-v` / `-vv` / `-q`; progress bars go to stderr and only in a terminal
- **Fast start** — commands import their dependencies on use; `undatum --help` takes ~0.15 s instead of ~0.8 s
- **Plugin commands** can be registered lazily through the `undatum.commands` entry point group
- **CI runs on `master`** (it was configured for `main` and never ran) with lint, tests on 3.10–3.13, base install without extras, clean-wheel smoke, lowest-dependency, deprecation, dependency audit and database integration jobs; coverage must stay at or above 65%
- **Release pipeline** — tests, clean install and binaries must pass before anything is published; `rc` tags go to TestPyPI; distributions and binaries carry build provenance attestations; release notes come from Conventional Commits via git-cliff (`cliff.toml`); binaries are also built on pull requests that touch `packaging/`
- **Tooling** — `ruff format` replaces black and pylint is dropped; tool versions are pinned once in the `dev` extra and checked against pre-commit and CI (`scripts/check_tool_versions.py`); `uv.lock` pins CI and binary builds
- **Dependencies** — every runtime dependency and extra has lower and upper bounds, checked in CI, and the lower bounds are tested on Python 3.10 (`lowest direct dependencies` job, now blocking). Direct dependencies on `tqdm`, `tabulate`, `chardet`, `xlwt`, `jsonlines`, `numpy`, `zipp` and `dnspython` were removed: progress bars and report tables use `rich`, encoding detection uses iterabledata. The base install is 62 packages (was 70)
- **Lint and types** — ruff also applies pylint (`PL`) rules and, for `undatum/cmds/` and `undatum/sdk/`, Google docstring (`D`) rules; mypy runs as a blocking ratchet (`mypy-baseline.json`, errors per file may only go down) with `undatum/common/` fully annotated
- **Repository** — `SECURITY.md`, issue and pull request templates, `CODEOWNERS`, and a workflow that auto-merges passing Dependabot patch updates (needs "Allow auto-merge" in the repository settings)
- **Streaming transforms** — `rename`, `fill`, `replace`, `search`, `head`, `tail`, `slice`, `enum`, `explode`, `exclude`, `fixlengths`, `fmt`, `cat`, `dedup`, `join` and `mask` no longer hold the dataset in memory: on 1M rows `rename` peaks at about 150 MB (was 800 MB) and memory no longer grows with the input. `reverse` and `fill --strategy backward` spill to disk; `transpose` holds one column at a time. CI checks the budget (300 MB for 1M rows)
- **DuckDB pushdown** — `rename`, `fill`, `replace`, `search`, `head` and `slice` run as one DuckDB query on CSV/TSV/JSON/JSON Lines/Parquet inputs (7x faster for `rename` on 1M CSV rows) and produce the same records as the Python engine (checked by contract tests); `--engine` is available on these commands
- **Faster commands on CSV/TSV/JSON/Parquet** — iterabledata (about 1 s to import, as it loads every format and database driver) is imported only when a command reads through it; DuckDB-backed runs skip it, so `undatum head data.csv` takes 0.7 s instead of 2.1 s
- **`s3://` reads stream** through s3fs when it is installed (`undatum[cloud]`) instead of downloading the object first
- **New `undatum.io` and `undatum.ops` packages** — typed (dataclass) operations with Python and SQL implementations, and one source/sink layer, shared by the CLI and (next) the SDK and agent tools
- **Faster `stats` on text columns** — date detection caches repeated values, skips values without digits and stops checking a column after 1,000 values unless at least half were dates: 15.5 s → 2.5 s on 100k rows with hash and free-text columns, with the same types reported
- **Commands that write `.csv`, `.json`, `.jsonl` or `.parquet` through DuckDB** no longer import iterabledata to look up the output format: `rename` and `fill` on 100k rows take 0.25 s and 86 MB (were 3 s and 165 MB); `count` takes 0.19 s on 500k rows (was 0.53 s) and uses the row count stored in ORC, Arrow and DBF files
- **One AI stack** — `--autodoc` on `analyze`, `schema`, `schema-bulk`, `doc` and `package create` uses iterabledata's providers, like `undatum ai`: `anthropic`, `gemini`, `azure` and `openai-compatible` now work there too (they disabled autodoc before), `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` select a provider when none is configured, and `--ai-model` also applies to field descriptions. Configuration names are unchanged
- **CLI code layout** — the data commands moved from one 3,800-line `undatum/cli/data_commands.py` to `undatum/cli/commands/` (one module per area: `convert`, `explore`, `describe`, `records`, `fields`, `combine`, `quality`, `query`), with shared option aliases in `undatum/cli/options.py`
- **Version** is defined only in `undatum/__init__.py`
- **Exit codes** are documented in the troubleshooting page and `man undatum` (0, 1, 2, 3, 4, 130)

### Removed

- **`undatum.common.iterable`** (`DataWriter`, `BSONWriter`) — write records with `undatum.common.writer` (`write_records`, `emit_records`, `StdoutSink`)
- **Legacy AI provider classes** — `undatum.ai.OpenAIProvider`, `OpenRouterProvider`, `OllamaProvider`, `LMStudioProvider`, `PerplexityProvider`, the abstract `undatum.ai.base.AIService`, and the modules `undatum.ai.providers`, `undatum.ai.perplexity` and `undatum.ai.schemas`. Use `undatum.ai.get_ai_service()`, which returns an `AIService` dataclass over `iterable.ai`
- **Legacy configuration** — `tox.ini`, `setup.cfg`, `flake8`, `requirements.txt` and `.coveragerc`; everything lives in `pyproject.toml`

### Added

- **Unix pipelines** — `-` as the input path reads standard input (format and `.gz`/`.zst`/`.bz2`/`.xz` compression detected from the first bytes, `--format-in` to override), e.g. `cat data.csv | undatum sort - --by a | undatum head - -n 3`. Record commands accept `--format-out`/`-O` for stdout; binary formats are refused on a terminal. Closing the pipe early (`| head -1`) exits with 0
- **SDK methods** — `Dataset.from_records()`, `replace()`, `exclude()`, `concat()`, `limit()`, `slice()`, `fixlengths()`, `transpose()`, `collect()`, `explain()`, `uniq()`, `frequency()`, `validate()` and `schema()`; `write()` runs the plan as one DuckDB query when every step has a SQL form
- **Agent tools for every operation** — MCP and LangChain get one tool per operation of the registry (`dedup`, `join`, `rename`, `sort`, ...), with JSON Schemas generated from the operation configs; results come back inline, or are written to `output_path` with `confirm=true`. `undatum mcp tools --parity` lists which CLI commands have a tool. LangChain tools now publish their argument schemas
- **Container image and packaging** — a `Dockerfile` (slim, non-root, `undatum` entrypoint; `--build-arg EXTRAS=full` for the common extras); release tags build, smoke-test and publish `ghcr.io/datenoio/undatum:<version>` and `:<version>-full` before PyPI publishing, and pull requests that touch the image build it. A Homebrew formula template with a release job (runs once a tap repository is configured) and a conda-forge recipe (waits for iterabledata on conda-forge) are in `packaging/`
- **`db load` into ClickHouse and SQL Server** — `clickhouse://` (batched inserts with `clickhouse-connect`, `--create-table` with inferred `Nullable` types and `--table-engine`, append and replace) and `mssql://` (pyodbc with `fast_executemany`, `--create-table`, append, replace and `MERGE`-based upsert); integration tests run against service containers in CI
- **MCP resources and prompts** — the MCP server lists the data files under its root (`undatum://datasets`), and serves each file's schema and sample (`undatum://dataset/{path}/schema`, `.../sample`) and the format catalogue (`undatum://formats`); prompts `profile-dataset`, `draft-validation-rules`, `plan-conversion` and `document-dataset` give clients ready plans. Works with mcp 1.x and 2.x; paths stay inside the sandbox root
- **`undatum quality`** — one report per dataset: per-field empty values, distinct and top values, type and type conformance; differences from an expected schema (`--schema`); rule violations by severity (`--rules`); and a pass/fail verdict from a thresholds file (`min_rows`, `max_null_rate`, `min_type_conformance`, `max_error_violations`, `schema: strict|additive`). Markdown, standalone HTML or JSON (`undatum.quality/1`); exits with 1 when a threshold fails, for CI. Also `Dataset.quality()` and `command: quality` in pipelines
- **Validation rule library** — rule files can use `format: date` (with `formats`), `datetime`, `phone` (E.164; national numbers with `region` and `undatum[phone]`), `country`, `currency`, `language` (ISO code lists bundled), `iban`, `uuid`, `pattern`, `integer`, `number`, `boolean`, plus `unique: true` and `references: {file, field}` (values must exist in another file); `undatum validate --list-rules` prints the catalogue and `-O jsonl` writes one violation per line. Violations in JSON have the keys `rule`, `field`, `severity`, `row`, `value`, `message`
- **Schema drift detection** — `diff --schema OLD NEW` (also `undatum schema diff`) reports added, removed, retyped and nullability-changed fields and likely renames (similar name or shared values); `schema-drift FILES... [--baseline schema.json]` (also `undatum schema drift`) checks a set of deliveries against a baseline data file, `undatum schema --json` output, JSON Schema or Frictionless schema. `--fail-on added,removed,type,nullability,any` exits with 1 for CI; text, Markdown and JSON reports
- **Partitioned output** — `convert data.csv out/ --partition-by year,month -O parquet` and `split --fields region --hive` write Hive-style `field=value/` directories readable by DuckDB, Spark, Athena and BigQuery, in any writable format (DuckDB `COPY ... PARTITION_BY` for CSV/Parquet, a streaming writer otherwise). `--max-open-files` (default 128) bounds open files, so high-cardinality keys work
- **SQL expressions** — `--where "amount > 100 AND city = 'Berlin'"` on `select`, `search`, `head`, `sample`, `count` and `convert`, and repeatable `--add "total = price * qty"` on `select` and `convert`. DuckDB evaluates them on typed values (text columns get the number, date or boolean type most of their values have) while the output keeps the original text; inputs DuckDB cannot read are evaluated in batches with the same results. Unknown columns are reported with suggestions; subqueries, table functions and `getenv` are refused. Also available as the `where` agent tool
- **`undatum migrate-script`** rewrites deprecated commands and options (`--filetype`, `--outtype`, `--n`, `--engine iterable`, `profile`, `document`, `scheme`) in shell scripts, Makefiles, Markdown and pipeline YAML to the current names; it shows a diff, `--write` applies it and `--check` fails CI while anything is left. A [migration guide](https://datenoio.github.io/undatum/getting-started/migrating-to-2) lists every change, including `ingest` → `db load`
- **Database steps in pipelines** — `command: db load` (also `db query`, `db dump`) replaces the deprecated `ingest` step
- **JSON output for informational commands** — `--json` (same as `--format-out json`) on `count`, `headers`, `sniff`, `stats`, `schema`, `diff`, `validate`, `analyze`, `formats list` and `config show` prints one JSON document with a versioned layout id (`"schema": "undatum.count/1"`). Layouts are documented on the [JSON output](https://datenoio.github.io/undatum/commands/json-output) page and published as JSON Schema files. In JSON mode errors are a JSON object on stderr (`{"error": {"code": "file_not_found", ...}}`) with the usual exit codes. Agent tools `count_records`, `list_fields`, `sniff_file` and `diff_files` return the same documents
- **Performance benchmarks** — `scripts/benchmarks.py` measures wall time and peak memory of 18 commands on generated 100k- and 1M-row CSV/JSON Lines/Parquet files, with per-command budgets in `tests/benchmarks/budgets.toml` (`make bench`). Pull requests are compared with the base branch on the same runner and fail on a regression above 20%; a nightly 1M-row run keeps a history chart on the documentation site
- **mcp 2.x** — the MCP server runs on both mcp 1.x (`FastMCP`) and 2.x (`MCPServer`)
- **`db load` into MongoDB and Elasticsearch/OpenSearch** — `--db mongodb://host/db` (collection = `--table`) and `--db elasticsearch://host:9200` / `opensearch://` (HTTPS; `+http` for plain HTTP; index = `--table`) with `--api-key`/`ELASTIC_API_KEY`, `--doc-id`, `--ca-cert`, `--insecure`, `--es-pipeline`, so the deprecated `ingest` is no longer needed

- **Docusaurus documentation site** — user docs live in `docs/` (content in `docs/docs/`), organized like iterabledata (getting started, use cases, CLI reference, formats, integrations, development), with GitHub Pages deployment at https://datenoio.github.io/undatum/
- **Shared CLI options page** — `--flatten-nested`, `--on-error`, `--error-log`, `--table`/`--sheet`, `--quotechar`, and `--filter` documented once and linked from convert and the command index
- **Pipeline YAML reference** — step `args` mapping, `$step_name`, `package` subcommands, and the `jsonl-normalization` template
- **MCP client config** — Cursor `mcp.json` / Claude Desktop examples and a tool catalog on the MCP docs
- **`undatum[dev]` extra** — pinned ruff and mypy, pytest, pytest-cov, pytest-benchmark, pre-commit (`make install-dev` uses it)

- **Generated reference** — every command page ends with a reference generated from the CLI (capabilities: formats read and written, memory use, engines; usage, arguments, options with types and defaults, deprecated spellings) and a new [Python SDK reference](https://datenoio.github.io/undatum/integrations/sdk-reference) is generated from the docstrings; CI fails when either is stale
- **Executable documentation** — every shell example in the docs runs in CI against fixture files (`scripts/run_doc_examples.py`); examples that need a server, cloud storage or an AI provider are marked `norun`
- **Development docs** — architecture, testing and releasing pages on the documentation site replace `openwiki/`; `AGENTS.md` is a short guide with links

### Changed

- **GitHub repository** moved from `datacoon/undatum` to [`datenoio/undatum`](https://github.com/datenoio/undatum). GitHub redirects the old URLs; documentation is at https://datenoio.github.io/undatum/
- **GCS and Azure cloud connectors** — first-class `gs://`/`gcs://` and `az://`/`abfs://`/`abfss://` URIs next to S3 for CLI, SDK, TUI/web, and Data API resources; extras `undatum[gcs]` and `undatum[azure]`; missing-extra errors name the install command
- **Docs accuracy** — `ai plan` takes two positional paths; Data API auth notes match `--api-key`; contributing install uses `make install-dev` / `.[dev]`; `llms.txt` and OpenWiki cover domain, operations, integrations, testing, and source maps; command write examples use `--output` (not a trailing positional path); `schema-bulk` hyphen; `ai filter` is expression then file; convert flattening is `--flatten-data`; replace is `--global-replace`; GitHub edit/blob links target `master`

### Fixed

- **`--filter` on select / validate / split / flatten / apply** — same flag as frequency / uniq / plot; `--filter-expr` remains an alias
- **Release binaries** — stop gitignoring `packaging/undatum.spec` so tagged PyInstaller jobs can find the spec

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

