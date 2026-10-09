---
title: "ingest"
description: "undatum ingest command reference"
---
# `ingest`

:::caution Deprecated
`ingest` is deprecated and will be removed in 2.0. Use [`db load`](/commands/db), which loads into the same databases (MongoDB and Elasticsearch/OpenSearch included) with `--db URI --table NAME`.
:::

Ingests data from files into databases. Supports MongoDB, PostgreSQL, DuckDB, MySQL, SQLite, and Elasticsearch with retry logic, progress tracking, and optional table auto-creation.

<!-- migrate-script: ignore -->

```bash norun
# Ingest to MongoDB
undatum ingest data.jsonl mongodb://localhost:27017 mydb mycollection
undatum ingest workbook.xlsx mongodb://localhost:27017 mydb cities --source-table Sheet2
undatum ingest nested.jsonl sqlite:///cities.db cities --dbtype sqlite --create-table --flatten-nested

# Ingest to PostgreSQL (append mode)
undatum ingest data.csv postgresql://user:pass@localhost:5432/mydb mytable --dbtype postgresql

# Ingest to PostgreSQL with auto-create table
undatum ingest data.jsonl postgresql://user:pass@localhost:5432/mydb mytable \
  --dbtype postgresql \
  --create-table

# Ingest to PostgreSQL with upsert (update on conflict)
undatum ingest data.jsonl postgresql://user:pass@localhost:5432/mydb mytable \
  --dbtype postgresql \
  --mode upsert \
  --upsert-key id

# Ingest to PostgreSQL (replace mode - truncates table first)
undatum ingest data.csv postgresql://user:pass@localhost:5432/mydb mytable \
  --dbtype postgresql \
  --mode replace

# Ingest to DuckDB (file database)
undatum ingest data.csv duckdb:///path/to/database.db mytable --dbtype duckdb

# Ingest to DuckDB (in-memory database)
undatum ingest data.jsonl duckdb:///:memory: mytable --dbtype duckdb

# Ingest to DuckDB with auto-create table
undatum ingest data.jsonl duckdb:///path/to/database.db mytable \
  --dbtype duckdb \
  --create-table

# Ingest to DuckDB with upsert
undatum ingest data.jsonl duckdb:///path/to/database.db mytable \
  --dbtype duckdb \
  --mode upsert \
  --upsert-key id

# Ingest to DuckDB with Appender API (streaming)
undatum ingest data.jsonl duckdb:///path/to/database.db mytable \
  --dbtype duckdb \
  --use-appender

# Ingest to MySQL
undatum ingest data.csv mysql://user:pass@localhost:3306/mydb mytable --dbtype mysql

# Ingest to MySQL with auto-create table
undatum ingest data.jsonl mysql://user:pass@localhost:3306/mydb mytable \
  --dbtype mysql \
  --create-table

# Ingest to MySQL with upsert
undatum ingest data.jsonl mysql://user:pass@localhost:3306/mydb mytable \
  --dbtype mysql \
  --mode upsert \
  --upsert-key id

# Ingest to SQLite (file database)
undatum ingest data.csv sqlite:///path/to/database.db mytable --dbtype sqlite

# Ingest to SQLite (in-memory database)
undatum ingest data.jsonl sqlite:///:memory: mytable --dbtype sqlite

# Ingest to SQLite with auto-create table
undatum ingest data.jsonl sqlite:///path/to/database.db mytable \
  --dbtype sqlite \
  --create-table

# Ingest to SQLite with upsert
undatum ingest data.jsonl sqlite:///path/to/database.db mytable \
  --dbtype sqlite \
  --mode upsert \
  --upsert-key id

# Ingest to Elasticsearch
undatum ingest data.jsonl https://elasticsearch:9200 myindex myindex --dbtype elasticsearch --api-key YOUR_API_KEY --doc-id id

# Ingest with options
undatum ingest data.csv mongodb://localhost:27017 mydb mycollection \
  --batch 5000 \
  --drop \
  --totals \
  --timeout 30 \
  --skip 100

# Ingest multiple files
undatum ingest "data/*.jsonl" mongodb://localhost:27017 mydb mycollection
```

**Key Features:**
- **Automatic retry**: Retries failed operations with exponential backoff (3 attempts)
- **Connection pooling**: Efficient connection management for all databases
- **Progress tracking**: Real-time progress bar with throughput (rows/second)
- **Error handling**: Continues processing after batch failures, logs detailed errors
- **Summary statistics**: Displays total rows, successful rows, failed rows, and throughput at completion
- **Connection validation**: Tests database connection before starting ingestion
- **PostgreSQL optimizations**: Uses COPY FROM for maximum performance (10-100x faster than INSERT)
- **Schema management**: Auto-create tables from data schema or validate existing schemas

**Options:**
- `--batch`: Batch size for ingestion (default: 1000, PostgreSQL recommended: 10000, DuckDB recommended: 50000, MySQL recommended: 10000, SQLite recommended: 5000)
- `--dbtype`: Database type: `mongodb` (default), `postgresql`, `postgres`, `duckdb`, `mysql`, `sqlite`, `elasticsearch`, or `elastic`
- `--drop`: Drop existing collection/table before ingestion (MongoDB, Elasticsearch)
- `--mode`: Ingestion mode for PostgreSQL/DuckDB/MySQL/SQLite: `append` (default), `replace`, or `upsert`
- `--create-table`: Auto-create table from data schema (PostgreSQL/DuckDB/MySQL/SQLite)
- `--upsert-key`: Field name(s) for conflict resolution in upsert mode (PostgreSQL/DuckDB/MySQL/SQLite, comma-separated for multiple keys)
- `--use-appender`: Use Appender API for DuckDB (streaming insertion, default: False)
- `--totals`: Show total record counts during ingestion (uses DuckDB for counting)
- `--timeout`: Connection timeout in seconds (positive values, default uses database defaults)
- `--skip`: Number of records to skip at the beginning
- `--api-key`: API key for database authentication (Elasticsearch)
- `--doc-id`: Field name to use as document ID (Elasticsearch, default: `id`)
- `--verbose`: Enable verbose logging output

**PostgreSQL-Specific Features:**
- **COPY FROM**: Fastest bulk loading method (100,000+ rows/second)
- **Upsert support**: `INSERT ... ON CONFLICT` for idempotent ingestion
- **Schema auto-creation**: Automatically creates tables with inferred types
- **Connection pooling**: Efficient connection reuse
- **Transaction management**: Atomic batch operations

**DuckDB-Specific Features:**
- **Fast batch inserts**: Optimized executemany for high throughput (200,000+ rows/second)
- **Appender API**: Streaming insertion for real-time data ingestion
- **Upsert support**: `INSERT ... ON CONFLICT` for idempotent ingestion
- **Schema auto-creation**: Automatically creates tables with inferred types
- **File and in-memory**: Supports both file-based and in-memory databases
- **No server required**: Embedded database, no separate server needed
- **Analytical database**: Optimized for analytical workloads and OLAP queries

**MySQL-Specific Features:**
- **Multi-row INSERT**: Efficient batch operations (10,000+ rows/second)
- **Upsert support**: `INSERT ... ON DUPLICATE KEY UPDATE` for idempotent ingestion
- **Schema auto-creation**: Automatically creates tables with inferred types
- **Connection management**: Efficient connection handling
- **Transaction support**: Atomic batch operations

**SQLite-Specific Features:**
- **PRAGMA optimizations**: Automatic performance tuning (synchronous=OFF, journal_mode=WAL)
- **Fast batch inserts**: Optimized executemany (10,000+ rows/second)
- **Upsert support**: `INSERT ... ON CONFLICT` for idempotent ingestion (SQLite 3.24+)
- **Schema auto-creation**: Automatically creates tables with inferred types
- **File and in-memory**: Supports both file-based and in-memory databases
- **No server required**: Embedded database, no separate server needed
- **Built-in**: Uses Python's built-in sqlite3 module, no dependencies required

**Error Handling:**
- Transient failures (connection timeouts, network errors) are automatically retried
- Partial batch failures are logged but don't stop ingestion
- Failed records are tracked and reported in the summary
- Detailed error messages help identify problematic data

**Performance:**
- Batch processing for efficient ingestion
- Connection pooling reduces overhead
- Progress tracking shows real-time throughput
- Optimized for large files with streaming support

**Example Output:**
```
Ingesting data.jsonl to mongodb://localhost:27017 with db mydb table mycollection
Ingesting to mongodb: 100%|████████████| 10000/10000 [00:05<00:00, 2000 rows/s]

Ingestion Summary:
  Total rows processed: 10000
  Successful rows: 10000
  Failed rows: 0
  Batches processed: 10
  Time elapsed: 5.00 seconds
  Average throughput: 2000 rows/second
```
