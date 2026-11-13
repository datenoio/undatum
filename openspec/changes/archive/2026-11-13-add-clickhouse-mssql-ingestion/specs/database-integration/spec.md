## ADDED Requirements

### Requirement: ClickHouse Load Target
The `db load` command SHALL load files into ClickHouse in batches, optionally creating the target
table from the inferred schema.

#### Scenario: Load Parquet into ClickHouse
- **WHEN** user runs `undatum db load events.parquet --db clickhouse://host/db --table events --create-table`
- **THEN** the table is created with a MergeTree engine and all rows are inserted

### Requirement: MS SQL Server Load Target
The `db load` command SHALL load files into MS SQL Server with append, replace and upsert modes.

#### Scenario: Upsert into SQL Server
- **WHEN** user runs `undatum db load orders.csv --db mssql://user:pass@host/db --table orders --mode upsert --upsert-key id`
- **THEN** existing rows with matching `id` are updated and new rows are inserted
