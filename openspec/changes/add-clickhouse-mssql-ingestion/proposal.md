# Change: Load Data into ClickHouse and MS SQL Server

## Why
`db query`/`db dump` read from ClickHouse and MS SQL Server (`undatum/cli/db_cli.py`), but
`db load` and `ingest` support only MongoDB, PostgreSQL, MySQL, DuckDB, SQLite and Elasticsearch.
Users who extract from one warehouse cannot load into these two with the same tool.

## What Changes
- ClickHouse loader (`clickhouse-driver` extra): batched native inserts, `--create-table` with
  inferred types and a configurable `ENGINE` (default `MergeTree ORDER BY tuple()`), append and
  replace modes.
- MS SQL Server loader (`pyodbc` extra): `fast_executemany` batches, `--create-table`, append,
  replace and upsert (`MERGE`) modes.
- Both stream input in batches and report progress like existing loaders.

## Impact
- Affected specs: `database-integration`
- Affected code: `undatum/cmds/ingester/`, `undatum/cli/db_cli.py`, `pyproject.toml` extras, docs
- CI: ClickHouse and SQL Server service containers in the DB integration job
