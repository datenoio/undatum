# undatum

[![PyPI](https://img.shields.io/pypi/v/undatum)](https://pypi.org/project/undatum/)
[![Python versions](https://img.shields.io/pypi/pyversions/undatum)](https://pypi.org/project/undatum/)
[![CI](https://github.com/datenoio/undatum/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/datenoio/undatum/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-datenoio.github.io%2Fundatum-blue)](https://datenoio.github.io/undatum/)
[![License: MIT](https://img.shields.io/pypi/l/undatum)](LICENSE)

> A command-line tool for data processing and analysis

**undatum** (pronounced *un-da-tum*) is a CLI for converting, analyzing, validating, and transforming datasets across many formats. Conversion, statistics, selection, validation and database loads stream records, so file size is not limited by memory; each [command page](https://datenoio.github.io/undatum/commands/) states how much memory the command needs.

## Features

- **140+ formats via iterabledata**: CSV, JSON, JSON Lines, BSON, XML, XLS/XLSX, Parquet, AVRO, ORC, plus geospatial, lakehouse (Delta/Iceberg/Lance/DuckLake/Paimon), scientific, RDF, log, config, graph, and feed formats. Run `undatum formats list` to see every supported format and its read/write capabilities.
- **Compression support**: GZ, XZ, BZ2, ZIP, ZSTD, LZ4, 7Z, Brotli, Snappy, LZO
- **Multi-cloud I/O**: Read and write `s3://`, `gs://`/`gcs://`, and `az://`/`abfs://`/`abfss://` URIs natively via iterabledata (`pip install "undatum[cloud]"`)
- **Databases**: Query and dump PostgreSQL, MySQL/MariaDB, SQLite, SQL Server, ClickHouse, MongoDB, and Elasticsearch/OpenSearch (`undatum db query`, `undatum db dump`); load files into DuckDB, SQLite, PostgreSQL, MySQL, ClickHouse, SQL Server, MongoDB, and Elasticsearch/OpenSearch (`undatum db load`, with create-table, replace and upsert where the database supports them)
- **Large files**: record commands stream with bounded memory; `sort`, `dedup` and `reverse` spill to disk; DuckDB runs SQL and many transforms out of core. Each [command page](https://datenoio.github.io/undatum/commands/) states its memory use (for example `uniq` and `frequency` grow with the number of distinct values)
- **Unix pipelines**: `-` reads standard input and results go to standard output in the input's format: `cat data.csv \| undatum sort - --by amount \| undatum head - -n 10`
- **SQL expressions**: `--where "amount > 100 AND city = 'Berlin'"` filters and `--add "total = price * qty"` adds computed fields on `select`, `convert` and other commands, evaluated by DuckDB on typed values
- **Partitioned output**: `undatum convert data.csv out/ --partition-by year,month -O parquet` writes Hive-style `field=value/` directories that DuckDB, Spark, Athena and BigQuery read
- **Automatic detection**: Encoding, delimiters (comma, semicolon, tab, pipe), headers, compression and file types
- **Data validation**: rule files with a built-in library — emails, URLs, dates, E.164 phones, ISO country/currency/language codes, IBAN, UUID, patterns, ranges, `unique` and `references` to another file (`undatum validate --rules`; `--list-rules` prints the catalogue)
- **Quality reports**: `undatum quality` profiles a dataset (empty values, distinct and top values, type conformance), checks it against an expected schema and rules, and fails CI when a threshold is not met (Markdown, HTML or JSON)
- **Schema drift**: `undatum diff --schema` and `undatum schema-drift` report added, removed, retyped and renamed fields across deliveries; `--fail-on` turns drift into a non-zero exit code
- **Machine-readable output**: `--json` on informational commands (`count`, `headers`, `sniff`, `stats`, `schema`, `diff`, `validate`, ...) prints versioned [JSON documents](https://datenoio.github.io/undatum/commands/json-output); errors become JSON too, with [documented exit codes](https://datenoio.github.io/undatum/getting-started/troubleshooting)
- **Frictionless Data Packaging**: Create, extend, and validate `datapackage.json` descriptors (`undatum package`)
- **Ad-hoc SQL on files**: Run DuckDB SQL over CSV, JSONL, Parquet, and other formats (`undatum sql`)
- **Python SDK**: a lazy `Dataset` API — chained steps build a plan that runs as one DuckDB query when every step has a SQL form
- **AI-powered tooling**: `undatum ai` and `--autodoc` on `analyze`, `schema` and `doc` share iterabledata's providers (OpenAI, Anthropic, Gemini, Azure, OpenRouter, Ollama, LM Studio, Perplexity, OpenAI-compatible endpoints); values in personal-data columns are masked in samples sent to remote providers
- **Agent tools & MCP server**: one tool per operation for MCP and LangChain; `undatum mcp serve` also exposes dataset listings, schemas and samples as resources and ships ready-made prompts (mcp 1.x and 2.x)
- **Optional TUI and web UI**: Explore a bounded sample in the terminal (`undatum tui`) or a local browser (`undatum web`)
- **Optional Data API**: Serve file-backed datasets over HTTP (FastAPI + DuckDB)

## Documentation

The full documentation site (Docusaurus) lives in [`docs/`](docs/) and is published at **[datenoio.github.io/undatum](https://datenoio.github.io/undatum/)**.

| Section | What it covers |
|---------|----------------|
| [Getting started](https://datenoio.github.io/undatum/getting-started/installation) | Install, quick start, positioning |
| [Cookbook](https://datenoio.github.io/undatum/getting-started/cookbook) | Task index by role |
| [CLI reference](https://datenoio.github.io/undatum/commands/) | Every command |
| [Formats](https://datenoio.github.io/undatum/formats/) | Honest capability matrix |
| [Python SDK](https://datenoio.github.io/undatum/integrations/sdk) | Fluent `Dataset` API |
| [MCP / agents](https://datenoio.github.io/undatum/integrations/mcp) | Agent tools and MCP server |
| [JSON output](https://datenoio.github.io/undatum/commands/json-output) | Versioned JSON layouts for scripts and agents |
| [Troubleshooting](https://datenoio.github.io/undatum/getting-started/troubleshooting) | Exit codes and common errors |
| [Migrating to 2.0](https://datenoio.github.io/undatum/getting-started/migrating-to-2) | Renamed commands and options, changed defaults |

Source pages: [`docs/docs/`](docs/docs/). Changelog: [`CHANGELOG.md`](CHANGELOG.md). Contributor workflow: [`WORKFLOW_GUIDE.md`](WORKFLOW_GUIDE.md).

## Installation

### Using uv or pipx (recommended for CLI use)

```bash
uv tool install undatum
# or
pipx install undatum
```

### Using pip

```bash
pip install --upgrade pip setuptools
pip install undatum
```

Dependencies are declared in `pyproject.toml` and will be installed automatically by modern versions of `pip` (23+), including **pyarrow** for Parquet.

### macOS

```bash
brew install pipx && pipx install undatum
# or
uv tool install undatum
```

Since 1.8.0, release tags also publish **PyInstaller single-file binaries** (Linux, macOS, Windows) on [GitHub Releases](https://github.com/datenoio/undatum/releases); 1.7.0 and earlier are on PyPI only. `pipx`/`uv` remain the supported install paths for most users.

A man page ships with the package (`man undatum` after install, or `make man` to regenerate `man/undatum.1`).

### Container

From the next release, images are published to GitHub Container Registry:

```bash
docker run --rm -v "$PWD:/data" ghcr.io/datenoio/undatum convert data.csv data.parquet
```

`:<version>` and `:latest` hold the core install, `:<version>-full` and `:latest-full` add the
common extras. A Homebrew tap and a conda-forge package are planned; see the
[installation guide](https://datenoio.github.io/undatum/getting-started/installation).

### Optional extras

| Extra | Enables |
|-------|---------|
| `api` | Data API server (`undatum api`, FastAPI + uvicorn + httpx) |
| `extract` | Document extraction (`undatum extract`, PDF/DOC/DOCX tables and text) |
| `plot` | Plotting (`undatum plot`, matplotlib) |
| `phone` | National phone numbers in validation rules (`format: phone` with `region`, phonenumbers) |
| `tui` | Interactive terminal UI (`undatum tui`, Textual) |
| `web` | Local web UI (`undatum web`, FastAPI + Jinja2) |
| `mcp` | MCP server for AI agents (`undatum mcp serve`) |
| `langchain` | LangChain agent tools |
| `polars`, `dask` | DataFrame interop from the `Dataset` SDK |
| `s3` | S3 cloud storage support (boto3) |
| `gcs` | Google Cloud Storage (`gs://` / `gcs://`, gcsfs) |
| `azure` | Azure Blob / ADLS (`az://` / `abfs://`, adlfs) |
| `cloud` | Multi-cloud storage via fsspec (S3 + GCS + Azure) |
| `postgres`, `mysql`, `mssql`, `clickhouse` | Database connectors (MongoDB is in the base install) |
| `elastic` | Elasticsearch / OpenSearch |
| `frictionless` | Full Frictionless Data Package validation |
| `lakehouse` | Delta / Iceberg / Lance / DuckLake / Hudi via iterabledata |
| `gis` | Geospatial and LiDAR formats |
| `scientific` | MATLAB, geophysical, and HDF5 formats |
| `access` | Microsoft Access (`.mdb` / `.accdb`) |
| `compression` | Extra codecs (snappy, brotli, lzo) |
| `all` | Every extra |

```bash
pip install "undatum[extract,api]"
```

After installation both `undatum` and the shorter `data` command are available:

```bash
undatum --version
undatum headers data.csv
data headers data.csv   # same thing
```

### Shell completion

```bash
undatum --install-completion   # for the shell you run it from (bash, zsh, fish, PowerShell)
undatum --show-completion      # print the script instead of installing it
```

### Requirements

- Python 3.10 or greater (CI tests 3.10–3.13)

### Install from source

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install .
```

## Quick start

```bash
# Inspect supported formats
undatum formats list --capabilities

# Convert
undatum convert people.csv people.parquet
undatum convert --tagname item data.xml data.jsonl

# Inspect
undatum headers data.jsonl
undatum analyze data.jsonl
undatum stats data.csv
undatum table data.csv --limit 20

# Query and transform
undatum sql "SELECT city, COUNT(*) AS n FROM data GROUP BY city" cities.csv
undatum select sales.csv --where "amount > 100" --add "total = price * qty" --output big.csv
undatum convert sales.csv sales/ --partition-by year -O parquet

# Pipelines: '-' reads stdin; CSV in, CSV out (-O jsonl to change it)
cat data.csv | undatum sort - --by amount --numeric amount | undatum head - -n 5

# Validate, check quality and drift, package
undatum validate data.csv --rules rules.yml
undatum quality data.csv --rules rules.yml --thresholds quality.yml --output report.html
undatum schema-drift deliveries/ --baseline schema.json --fail-on removed,type
undatum package create data.csv --output datapackage.json

# JSON for scripts and agents
undatum count data.csv --json

# Document
undatum ai doc data.csv
undatum doc data.jsonl --format-out markdown --output dataset.md
```

More first-success paths: [quick start](https://datenoio.github.io/undatum/getting-started/quick-start) and the [cookbook](https://datenoio.github.io/undatum/getting-started/cookbook).

## Commands

All commands are available as `undatum <command>` or via the shorter `data` alias.

**Top-level data commands:** `convert`, `extract`, `analyze`, `doc`, `stats`, `validate`, `quality`, `schema`, `schema-bulk`, `schema-drift`, `diff`, `sql`, `select`, `search`, `mask`, `plot`, `tui`, `web`, `migrate-script`, and the other transform/inspection commands in the [CLI reference](https://datenoio.github.io/undatum/commands/).

**Upgrading:** the older names `document`, `profile`, `ingest` and `scheme` and the old option spellings (`--filetype`, `--outtype`, `--n`, ...) still work with a deprecation warning until 2.0 (use `doc`, `stats`, `db load`, `schema --format cerberus`). `undatum migrate-script scripts/ --write` rewrites them in shell scripts, Makefiles, Markdown and pipeline YAML; the [migration guide](https://datenoio.github.io/undatum/getting-started/migrating-to-2) and the [changelog](CHANGELOG.md) list the changed defaults.

**Command groups:**

| Group | Subcommands |
|-------|-------------|
| `ai` | `doc`, `filter`, `plan`, `suggest` |
| `api` | `discover`, `serve`, `run`, `openapi` |
| `db` | `query`, `load`, `dump` |
| `package` | `create`, `add-resource`, `validate` |
| `pipeline` | `run`, `validate`, `doc`, `templates list`, `templates init` |
| `formats` | `list`, `describe`, `export`, `tables` |
| `mcp` | `serve`, `tools` |
| `examples` | `list`, `show`, `run` |
| `plugins` | `list`, `info`, `validate` |
| `config` | `show` |

```bash
undatum convert --help
undatum sql --help
```

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) and the [development docs](https://datenoio.github.io/undatum/development/contributing).

## License

MIT License — see [LICENSE](LICENSE).

## Links

- [Documentation](https://datenoio.github.io/undatum/)
- [GitHub](https://github.com/datenoio/undatum)
- [PyPI](https://pypi.org/project/undatum/)
- [Changelog](CHANGELOG.md)
- [Issue tracker](https://github.com/datenoio/undatum/issues)
- [iterabledata](https://github.com/datenoio/iterabledata) (streaming I/O engine)
