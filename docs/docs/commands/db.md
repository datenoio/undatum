---
title: "db"
description: "undatum db command reference"
---
# `db`

Database query, load, and dump commands for working with databases as first-class data sources and sinks. See also [`db dump`](/commands/db) below.

#### `db query`

Execute SQL queries against databases and output results in multiple formats.

```bash norun
# Query PostgreSQL and output JSONL
undatum db query "SELECT * FROM users LIMIT 100" --db postgresql://user:pass@host/db

# Query MySQL and save to file
undatum db query "SELECT name, email FROM customers WHERE status='active'" \
  --db mysql://user:pass@host:3306/mydb \
  --output results.jsonl

# Query SQLite and output CSV
undatum db query "SELECT * FROM data" --db sqlite:///path/to/db.db --format-out csv

# Query from SQL file
undatum db query --query-file query.sql --db postgresql://user:pass@host/db --output results.jsonl

# Output Parquet format
undatum db query "SELECT * FROM large_table" --db postgresql://... --format-out parquet --output data.parquet
```

**Supported Databases:**

| Engine | URI scheme | Notes |
|--------|------------|-------|
| PostgreSQL | `postgresql://user:pass@host:port/db` | Native driver |
| MySQL / MariaDB | `mysql://user:pass@host:port/db` | Native driver |
| SQLite | `sqlite:///path/to/db.db`, `sqlite:///:memory:` | Native driver |
| MS SQL Server | `mssql://`, `sqlserver://` | Via iterabledata; `pip install "undatum[mssql]"` |
| ClickHouse | `clickhouse://user:pass@host:9000/db` | Via iterabledata; `pip install "undatum[clickhouse]"` |
| MongoDB | `mongodb://host:27017/db?collection=name&limit=N` | Read-only; pass collection/limit in URI query string |
| Elasticsearch / OpenSearch | `elasticsearch://`, `opensearch://` | Read-only; pass `index=` in URI query string |

```bash norun
# ClickHouse
undatum db query "SELECT * FROM events LIMIT 100" --db clickhouse://user:pass@host:9000/db

# MongoDB collection (empty SQL argument; collection in URI)
undatum db query "" --db "mongodb://host:27017/mydb?collection=users&limit=100"

# Elasticsearch index
undatum db query "" --db "elasticsearch://host:9200?index=logs&limit=100"
```

**Output Formats:**
- `jsonl` (default) - JSON Lines format, one record per line
- `csv` - Comma-separated values format
- `parquet` - Parquet format (requires pandas and pyarrow)

**Features:**
- **Streaming support**: Results are streamed in batches for efficient memory usage
- **Large result sets**: Handles queries returning millions of rows
- **Server-side cursors**: Uses PostgreSQL named cursors for optimal performance
- **Column inference**: Automatically detects column names from query results

#### `db load`

Load a data file into a database table, collection or search index. The database type comes from the URI scheme.

```bash norun
# Load data to PostgreSQL (append mode)
undatum db load data.parquet --db postgresql://user:pass@host/db --table users

# Load with replace mode
undatum db load data.csv --db mysql://user:pass@host:3306/mydb --table customers --mode replace

# Load with upsert
undatum db load data.jsonl --db postgresql://user:pass@host/db --table orders --mode upsert --upsert-key id

# Auto-create table from schema
undatum db load data.parquet --db sqlite:///db.db --table new_table --create-table
undatum db load workbook.xlsx --db sqlite:///db.db --table cities --source-table Sheet2 --create-table
undatum db load quoted.csv --db sqlite:///db.db --table people --create-table --quotechar "'"
undatum db load nested.jsonl --db sqlite:///db.db --table cities --create-table --flatten-nested

# MongoDB: the database is the URI path, --table is the collection
undatum db load orders.jsonl --db mongodb://localhost:27017/shop --table orders --mode replace

# Elasticsearch / OpenSearch: --table is the index (HTTPS by default)
export ELASTIC_API_KEY=...
undatum db load logs.jsonl --db elasticsearch://search.example.org:9200 --table logs --doc-id event_id
undatum db load logs.jsonl --db opensearch+http://localhost:9200 --table logs

# ClickHouse (HTTP interface; clickhouses:// for HTTPS)
undatum db load events.parquet --db clickhouse://user:pass@ch.example.org:8123/analytics \
  --table events --create-table --table-engine "MergeTree ORDER BY (day, id)"

# SQL Server: upsert with MERGE
undatum db load customers.csv --table dbo.customers --mode upsert --upsert-key id \
  --db "mssql://loader:secret@sql.example.org:1433/crm?TrustServerCertificate=yes"
```

**Supported Databases:**
- PostgreSQL, MySQL/MariaDB, SQLite, DuckDB
- ClickHouse (`append`, `replace`; needs `pip install "undatum[clickhouse]"`). `--create-table`
  creates a `MergeTree ORDER BY tuple()` table with `Nullable` columns where values were
  missing; `--table-engine` sets another engine.
- Microsoft SQL Server (`append`, `replace`, `upsert` with `MERGE`; needs
  `pip install "undatum[mssql]"` and the Microsoft ODBC Driver for SQL Server). Batches use
  `fast_executemany`, one transaction per batch.
- MongoDB (`append`, `replace`)
- Elasticsearch and OpenSearch (`append`; needs `pip install "undatum[elastic]"`). TLS
  certificates are verified; use `--ca-cert` for a private CA or `--insecure` to skip the
  check. `--api-key` (or `ELASTIC_API_KEY`), `--doc-id` (default `id`) and `--es-pipeline`
  apply to these targets only. The `elasticsearch` client must match the server's major
  version: for an Elasticsearch 8 server, install `pip install "elasticsearch>=8,<9"`
  (client 9 is rejected with `media_type_header_exception`).

**Load Modes:**
- `append` (default) - Add records to existing table
- `replace` - Replace all data in table (MongoDB: drop the collection first)
- `upsert` - Update existing records or insert new ones (requires `--upsert-key`; SQL databases only)

`--create-table` infers column types from the first batch: whole numbers, numbers and
`true`/`false` text become numeric and boolean columns; codes with leading zeros (`007`) stay
text. If rows cannot be loaded, the command finishes the other batches and then exits with
code 3, naming the first failure.

`db load` replaces the deprecated `ingest` command, which keeps working with a warning until 2.0.

**Database URI Formats:**

- **PostgreSQL**: `postgresql://user:password@host:port/database`
- **MySQL**: `mysql://user:password@host:port/database`
- **SQLite**: `sqlite:///path/to/db.db` or `sqlite:///:memory:`
- **ClickHouse**: `clickhouse://user:password@host:8123/database` (HTTP), `clickhouses://` (HTTPS)
- **SQL Server**: `mssql://user:password@host:1433/database?TrustServerCertificate=yes`; other
  query parameters become ODBC keywords, `driver=` picks the ODBC driver (default
  `ODBC Driver 18 for SQL Server`); without a user name Windows authentication is used
- **MongoDB**: `mongodb://user:password@host:port/database` (or `mongodb+srv://...`)
- **Elasticsearch / OpenSearch**: `elasticsearch://host:9200`, `opensearch://host:9200` (HTTPS);
  `elasticsearch+http://host:9200` for plain HTTP

#### `db dump`

Dump a database table or query result to a file. Results are streamed in batches for efficient memory usage; prefer Parquet for large dumps.

```bash norun
# Dump a whole table to Parquet
undatum db dump --db sqlite:///data.db --table users --output users.parquet

# Dump a query result to CSV
undatum db dump --db postgresql://user:pass@host/db --query "SELECT * FROM events" \
  --output events.csv --to csv

# Tune streaming batch size
undatum db dump --db mysql://user:pass@host:3306/mydb --table orders \
  --output orders.jsonl --to jsonl --batch-size 50000
```

**Options:**
- `--db` (required) - Database connection URI (same schemes as `db query`)
- `--output` (required) - Output file path
- `--table` - Table name to dump (alternative to `--query`)
- `--query` - SQL query to dump (alternative to `--table`)
- `--to` - Output format: `parquet` (default), `csv`, or `jsonl`
- `--batch-size` - Batch size for streaming results (default: 10000)

<!-- BEGIN GENERATED: reference -->
<!-- Generated by scripts/generate_cli_reference.py from the CLI; do not edit by hand. -->

## Reference

### `undatum db query`

**Reads:** a database query · **Writes:** any writable format; CSV/TSV/JSON/JSON Lines on stdout · **Memory:** streaming (batches) · **Engines:** python

```text
undatum db query [OPTIONS] QUERY
```

| Argument | Description |
|----------|-------------|
| `QUERY` | SQL query to execute. (required) |

| Option | Description | Default |
|--------|-------------|---------|
| `--db` TEXT | Database connection URI (e.g., postgresql://user:pass@host:port/db). (required) |  |
| `-o`, `--output` TEXT | Output file path. If not specified, prints to stdout. |  |
| `-O`, `--format-out` TEXT | Output format: 'jsonl' (default), 'csv', or 'parquet'. | `jsonl` |
| `--query-file` TEXT | Path to SQL query file (alternative to query argument). |  |
| `--batch-size` INTEGER | Batch size for streaming results (default: 10000). | `10000` |
| `--verbose` / `--no-verbose` | Enable verbose logging output. | `--no-verbose` |

Deprecated spellings (removed in 2.0): `--output-format` → `--format-out`.

### `undatum db load`

**Reads:** any readable format · **Writes:** a database table, collection or index · **Memory:** streaming · **Engines:** python

```text
undatum db load [OPTIONS] INPUT_FILE
```

| Argument | Description |
|----------|-------------|
| `INPUT_FILE` | Path to input file to load. (required) |

| Option | Description | Default |
|--------|-------------|---------|
| `--db` TEXT | Database connection URI (e.g., postgresql://user:pass@host:port/db). (required) |  |
| `--table` TEXT | Target table name. (required) |  |
| `--mode` TEXT | Load mode: 'append' (default), 'replace', or 'upsert'. | `append` |
| `--create-table` / `--no-create-table` | Auto-create table from data schema if it doesn't exist. | `--no-create-table` |
| `--upsert-key` TEXT | Key field(s) for upsert mode (comma-separated). |  |
| `--sheet`, `--source-table` TEXT | Source table or sheet name for multi-table files (Excel, SQLite, lakehouse). |  |
| `--start-page` INTEGER | Sheet index (0-based) for Excel files. | `0` |
| `--trust` | Acknowledge pickle deserialization risk when reading pickle sources. |  |
| `--on-error` TEXT | Parse-error policy: raise (default), skip, or warn. |  |
| `--error-log` TEXT | Append parse errors as JSONL (use with --on-error skip or warn). |  |
| `--quotechar` TEXT | CSV quote character (iterabledata default '"' when omitted). |  |
| `--flatten-nested` | Unfold nested dict / array-of-dict fields into dotted paths (e.g. city.lat). |  |
| `--max-nested-depth` INTEGER | With --flatten-nested, maximum nest depth to unfold (engine default 5). |  |
| `--keep-nested-parents` / `--no-keep-nested-parents` | With --flatten-nested, keep parent dict/array fields alongside dotted children. | `--keep-nested-parents` |
| `--api-key` TEXT | Elasticsearch/OpenSearch API key (or set ELASTIC_API_KEY). |  |
| `--doc-id` TEXT | Field used as the document ID (Elasticsearch). |  |
| `--insecure` | Disable TLS certificate verification (Elasticsearch). Not recommended. |  |
| `--ca-cert` TEXT | CA bundle for TLS verification (Elasticsearch). |  |
| `--es-pipeline` TEXT | Elasticsearch ingest pipeline to apply. |  |
| `--table-engine` TEXT | ClickHouse ENGINE for --create-table (default: MergeTree ORDER BY tuple()). |  |
| `--verbose` / `--no-verbose` | Enable verbose logging output. | `--no-verbose` |

### `undatum db dump`

**Reads:** a database table or query · **Writes:** any writable format; CSV/TSV/JSON/JSON Lines on stdout · **Memory:** streaming (batches) · **Engines:** python

```text
undatum db dump [OPTIONS]
```

| Option | Description | Default |
|--------|-------------|---------|
| `--db` TEXT | Database connection URI (e.g., postgresql://user:pass@host:port/db). (required) |  |
| `-o`, `--output` TEXT | Output file path. (required) |  |
| `--table` TEXT | Table name to dump (use with --to / output format). |  |
| `--query` TEXT | SQL query to dump (alternative to --table). |  |
| `--to` TEXT | Output format: 'parquet' (default), 'csv', or 'jsonl'. | `parquet` |
| `--batch-size` INTEGER | Batch size for streaming results (default: 10000). | `10000` |
| `--verbose` / `--no-verbose` | Enable verbose logging output. | `--no-verbose` |

See also [shared options](/commands/shared-options).
<!-- END GENERATED: reference -->
