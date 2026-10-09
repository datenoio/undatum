---
title: "SQL and analytics"
description: "Inspect files, run DuckDB SQL, and plot results"
---
# SQL and analytics

Inspect unfamiliar files and answer questions without writing a program.

## Understand a newly received dataset

```bash norun
undatum table sales.csv --limit 20
undatum tui sales.csv
undatum web sales.csv
undatum stats sales.csv
undatum frequency sales.csv --fields region,status
```

`tui` and `web` need extras: `pip install "undatum[tui]"` / `"undatum[web]"`.

## Filter without writing a query

`--where` takes a SQL condition on `select`, `search`, `head`, `sample`, `count` and `convert`
and keeps the original values in the output:

```bash
undatum count sales.csv --where "amount > 100"
undatum select sales.csv --where "amount > 100" --add "net = amount * 0.8" --fields name,amount,net
```

## Ad-hoc SQL across files

A single input is the view `data`; multiple inputs are named after their file stems.

```bash
undatum sql "SELECT region, SUM(amount) AS total FROM data GROUP BY 1" sales.parquet \
  --output totals.csv --format-out csv

undatum sql "SELECT * FROM orders JOIN users USING (user_id)" orders.csv users.parquet
```

## Plot

```bash
pip install "undatum[plot]"
undatum plot sales.csv --field amount --type histogram --output amount.png
```

See [`sql`](/commands/sql), [`stats`](/commands/stats), [`plot`](/commands/plot), [`tui`](/commands/tui), and [`web`](/commands/web).
