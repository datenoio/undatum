## 1. Loaders
- [x] 1.1 ClickHouse backend (batch insert, create table, append/replace) — with
      `clickhouse-connect` (the driver already used for `clickhouse://` sources) instead of
      `clickhouse-driver`
- [x] 1.2 MS SQL Server backend (fast_executemany, create table, append/replace/upsert)
- [x] 1.3 Type mapping from inferred schema for both

## 2. Tests and docs
- [x] 2.1 Integration tests with service containers (ClickHouse and SQL Server services in the
      `db-integration` CI job; not run locally — first run in CI)
- [x] 2.2 Update `docs/docs/commands/db.md`
