---
title: "Installation"
description: "Install undatum with uv, pipx, pip, or from source"
---
# Installation

### Using uv or pipx (recommended for CLI use)

```bash norun
uv tool install undatum
# or
pipx install undatum
```

### Using pip

```bash
pip install --upgrade pip setuptools
pip install undatum
```

Dependencies are declared in `pyproject.toml` and will be installed automatically by modern versions of `pip` (23+), including **pyarrow** for Parquet. If you see missing-module errors after installation, upgrade `pip` and retry.

### macOS

Preferred paths:

```bash norun
brew install pipx && pipx install undatum
# or
uv tool install undatum
```

A Homebrew tap is planned (`brew install datenoio/tap/undatum`); until it exists, use `pipx` or `uv` on macOS.

Release tags publish **PyInstaller single-file binaries** (Linux, macOS, Windows) on the [GitHub Releases](https://github.com/datenoio/undatum/releases) page (Actions artifacts on the tag workflow). These are ops-oriented; `pipx`/`uv` remain the supported install paths for most users.

A man page ships with the package (`man undatum` after install, or `make man` to regenerate `man/undatum.1`).

### Container image

Starting with the next release, every version is published as a container image (core
install and a `-full` variant with the common extras: API, web UI, MCP, cloud storage,
PostgreSQL, MySQL, ClickHouse, Elasticsearch, plots):

```bash norun
docker run --rm -v "$PWD:/data" ghcr.io/datenoio/undatum convert data.csv data.parquet
docker run --rm -v "$PWD:/data" ghcr.io/datenoio/undatum:latest-full mcp serve --root /data
```

The image runs as a non-root user with `/data` as the working directory; `undatum` is the
entrypoint. Build it yourself with `docker build -t undatum .` (`--build-arg EXTRAS=full`).

### Every channel at a glance

| Channel | Command | Status |
|---------|---------|--------|
| PyPI (uv / pipx / pip) | `uv tool install undatum` | available |
| Container | `docker run ghcr.io/datenoio/undatum --version` | from the next release |
| Release binaries | download from GitHub Releases | from the next release |
| Homebrew tap | `brew install datenoio/tap/undatum` | planned (the tap repository is not set up yet) |
| conda-forge | `conda install -c conda-forge undatum` | planned (waits for iterabledata on conda-forge) |

The same smoke test works for every channel: `undatum --version` and
`undatum count data.csv`.

### Optional extras

Some features require optional dependencies, installed as extras. This is the canonical list; feature sections elsewhere in the docs link back here. A command whose extra is missing exits with code 2 and prints the `pip install` command to run.

| Extra | Enables |
|-------|---------|
| `api` | Data API server (`undatum api`, FastAPI + uvicorn + httpx) |
| `extract` | Document extraction (`undatum extract`, PDF/DOC/DOCX tables and text) |
| `plot` | Plotting (`undatum plot`, matplotlib) |
| `tui` | Interactive terminal UI (`undatum tui`, Textual) |
| `web` | Local web UI (`undatum web`, FastAPI + Jinja2) |
| `mcp` | MCP server for AI agents (`undatum mcp serve`) |
| `langchain` | LangChain agent tools |
| `polars`, `dask` | DataFrame interop from the `Dataset` SDK |
| `s3` | S3 cloud storage support (boto3) |
| `gcs` | Google Cloud Storage (`gs://` / `gcs://`, gcsfs) |
| `azure` | Azure Blob / ADLS (`az://` / `abfs://`, adlfs) |
| `cloud` | Multi-cloud storage via fsspec (S3 + GCS + Azure) |
| `postgres`, `mysql`, `mssql`, `clickhouse` | Database connectors (MongoDB support is included in the base install) |
| `elastic` | Elasticsearch / OpenSearch (`db load`, `elasticsearch://` URIs) |
| `phone` | National phone numbers in validation rules (`format: phone` with `region`, phonenumbers) |
| `frictionless` | Full Frictionless Data Package validation |
| `lakehouse` | Delta / Iceberg / Lance / DuckLake / Hudi via iterabledata |
| `gis` | Geospatial and LiDAR formats |
| `scientific` | MATLAB, geophysical, and HDF5 formats |
| `access` | Microsoft Access (`.mdb` / `.accdb`) |
| `compression` | Extra codecs (snappy, brotli, lzo) |
| `all` | Every extra above |

```bash
pip install "undatum[api]"
pip install "undatum[extract]"
pip install "undatum[plot]"
pip install "undatum[tui]"
pip install "undatum[web]"
pip install "undatum[mcp]"
pip install "undatum[langchain]"
pip install "undatum[polars]"
pip install "undatum[dask]"
pip install "undatum[s3]"
pip install "undatum[gcs]"
pip install "undatum[azure]"
pip install "undatum[cloud]"
pip install "undatum[postgres]"
pip install "undatum[mysql]"
pip install "undatum[mssql]"
pip install "undatum[clickhouse]"
pip install "undatum[elastic]"
pip install "undatum[phone]"
pip install "undatum[frictionless]"
pip install "undatum[lakehouse]"
pip install "undatum[gis]"
pip install "undatum[scientific]"
pip install "undatum[access]"
pip install "undatum[compression]"
pip install "undatum[all]"

# Combine extras in one install
pip install "undatum[extract,api]"
```

After installation both `undatum` and the shorter `data` command are available:

```bash
undatum --version
undatum headers data.csv
data headers data.csv   # same thing
```

### Shell completion

Shell completion is built in. Run this from the shell you want completion for (bash, zsh,
fish or PowerShell); the shell is detected automatically:

```bash norun
undatum --install-completion
```

To print the completion script instead of installing it:

```bash norun
undatum --show-completion
```

### Requirements

- Python 3.10 or greater (CI tests 3.10–3.13)

### Install from source

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install .
# or build distributables
python -m pip install build && python -m build

# Contributors
make install-dev
# or: pip install -e ".[dev]"
```

## Next steps

- [Quick start](/getting-started/quick-start)
- [When to use undatum](/getting-started/when-to-use)
- [Format support](/formats/)
