---
title: "Data pipelines"
description: "Repeatable convert, clean, and load workflows"
---
# Data pipelines

Build repeatable, streaming transformations across formats, databases, and object storage.

## Normalize a raw delivery

```bash
undatum convert raw.jsonl.zst stage.parquet --low-memory
undatum dedup stage.parquet --key-fields id --output clean.parquet
undatum stats clean.parquet
```

## Chain commands with pipes

`-` reads standard input, and record commands write the input's format to standard output:

```bash
cat data.csv | undatum select - --where "amount > 50" | undatum sort - --by amount --numeric amount
```

## Write a partitioned lake layout

```bash
undatum convert data.csv lake --partition-by country -O parquet
```

DuckDB, Spark, Athena and BigQuery read the `country=DE/` directories as a partitioned table.

## Stop on schema changes

```bash
undatum schema-drift data.csv data.jsonl --fail-on removed,type
```

## YAML pipeline

```bash
undatum pipeline templates list
undatum pipeline templates init basic-cleaning --var input_file=data.csv
undatum pipeline templates init jsonl-normalization --output normalize.yml
undatum pipeline validate my-pipeline.yml
undatum pipeline run my-pipeline.yml
```

## Database round-trip

```bash norun
undatum db dump --db postgresql://user:pass@host/db --query "SELECT * FROM events" \
  --output events.parquet --to parquet

undatum db load clean.parquet --db postgresql://user:pass@host/db \
  --table events --mode upsert --upsert-key id
```

`db load` also writes to MySQL, SQLite, ClickHouse, SQL Server, MongoDB and
Elasticsearch/OpenSearch, and exits with 3 when any batch fails. Pipelines use the same
command as a step (`command: db load`).

See [`pipeline`](/commands/pipeline) for the YAML DSL (`steps`, `args`, `$step_name`), [`db`](/commands/db), and [cloud storage](/integrations/cloud).
