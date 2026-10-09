---
title: "Quick Start"
description: "Task-oriented first success paths for undatum"
---
# Quick Start

Short task-oriented paths to first success. Not sure where to start? Pick your
role and goal in the [cookbook](/getting-started/cookbook). Installation details:
[Installation](/getting-started/installation). CLI flag list: [CLI reference](/commands/).

## CSV → Parquet in 30 seconds

```bash
pip install undatum   # or: uv tool install undatum
printf 'name,age,city\nAda,36,London\nGrace,85,NYC\n' > people.csv
undatum convert people.csv people.parquet
undatum stats people.parquet
```

For multi-GB inputs:

```bash
undatum convert huge.jsonl.zst huge.parquet --low-memory
```

## Validate a dataset before publishing

Describe your expectations in a rules file, then validate against it:

```bash
cat > rules.yml <<'EOF'
rules:
  - field: email
    name: Email format
    required: true
    type: string
    format: email
    severity: error
EOF

undatum validate data.csv --rules rules.yml
undatum analyze data.csv
undatum package create data.csv --output datapackage.json
```

For a one-off check without a rules file, use legacy single-rule mode:

```bash
undatum validate data.csv --fields email --rule common.email
```

## Check quality and schema changes in CI

`quality` writes one report per dataset and exits with 1 when a threshold fails;
`schema-drift` compares new deliveries with a baseline:

```bash
undatum quality data.csv --rules rules.yml -o report.html
undatum schema-drift data.csv data.jsonl --fail-on removed,type
undatum count data.csv --json
```

`--json` prints a [versioned JSON document](/commands/json-output) for scripts and agents.

## Filter with SQL expressions and pipes

`--where` keeps the rows for which a SQL condition is true and `--add` computes columns; `-`
reads standard input, so commands chain without temporary files:

```bash
undatum select data.csv --where "amount > 100 AND city = 'Berlin'" --add "total = price * quantity"
cat data.csv | undatum sort - --by amount --numeric amount --desc | undatum head - -n 3
```

## Query JSONL with SQL

`undatum sql` takes the query first, then the input file(s). A single input is
available as the view `data`; multiple inputs are named after their file stems.

```bash
undatum sql "SELECT city, COUNT(*) AS n FROM data GROUP BY 1" events.jsonl
# or use frequency / select for simpler extractions:
undatum frequency events.jsonl --fields city
undatum select --fields id,city,ts --filter '`city` == "Berlin"' events.jsonl
```

## Dump a database table to Parquet

```bash
undatum db dump --db sqlite:///app.db --table users --output users.parquet --to parquet
```

## Next steps

- [Usage scenarios by role](/getting-started/cookbook) — task-oriented index for analysts, engineers, publishers, and more
- [Format support matrix](/formats/) — 140+ formats, lakehouse/open-data notes, extras
- [When to use undatum](/getting-started/when-to-use)
- [Large files](/getting-started/performance)
- [Error handling and exit codes](/getting-started/troubleshooting)
- [Upgrading from 1.x](/getting-started/migrating-to-2)
