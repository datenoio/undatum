---
title: "Cheat sheet"
description: "One-line undatum commands for common data tasks"
---
# Cheat sheet

One line per task. Every command reads CSV, JSON Lines, Parquet, Excel and the other
[formats](/formats) the same way; records go to stdout in the input's format, or to
`--output` in the format of its extension.

## Look at a file

```bash
undatum headers data.csv
undatum head data.csv -n 5
undatum table data.csv --fields name,city
undatum count data.csv
undatum sniff data.csv
undatum stats data.csv
undatum schema data.csv
undatum formats tables workbook.xlsx
```

## Choose columns and rows

```bash
undatum select data.csv --fields name,city
undatum select data.csv --where "amount > 100 AND city = 'Berlin'"
undatum search data.csv --fields city --pattern '^B'
undatum count data.csv --where "status = 'active'"
undatum slice data.csv --start 2 --end 4
undatum tail data.csv -n 3
undatum sample data.csv -n 3
```

## Sort, deduplicate and count values

```bash
undatum sort data.csv --by amount --numeric amount --desc
undatum dedup data.csv --key-fields city
undatum uniq data.csv --fields city
undatum frequency data.csv --fields city,status
```

## Change values and columns

```bash
undatum select data.csv --add "total = price * quantity"
undatum rename data.csv --map name:full_name
undatum replace data.csv --field city --pattern Berlin --replacement BER
undatum fill data.csv --fields tags --strategy forward
undatum explode data.csv --field tags --separator ,
undatum enum data.csv --type uuid --field uuid
undatum mask data.csv --fields email
undatum transpose data.csv
```

## Combine files

```bash
undatum join people.csv orders.csv --on id --type left
undatum exclude data.csv blacklist.csv --on id
undatum cat people.csv orders.csv
undatum diff people.csv orders.csv --key id
```

## Convert, split and reformat

```bash
undatum convert data.csv data.parquet
undatum convert data.csv data.jsonl.gz
undatum convert workbook.xlsx cities.csv --table Cities
undatum split data.csv --fields city --dirname by-city
undatum split data.csv --chunksize 3 --dirname parts
undatum fmt data.csv --delimiter ';'
```

## SQL

```bash
undatum sql "SELECT city, avg(amount) AS avg_amount FROM data GROUP BY city" data.csv
undatum sql "SELECT * FROM orders JOIN users USING (user_id)" orders.csv users.parquet
```

## Check quality

```bash
undatum validate data.csv --rules rules.yml
undatum quality data.csv
undatum schema-drift people.csv --baseline data.csv
```

## Pipelines

Commands read stdin when the input is `-`:

```bash
undatum select data.csv --where "amount > 50" | undatum frequency - --fields city
undatum head data.csv -n 100 | undatum stats -
```

## Scripts and agents

```bash
undatum count data.csv --json
undatum stats data.csv --json
undatum commands --search duplicate
undatum commands count --json
```

Coming from another tool? See [csvkit](/getting-started/from-csvkit) and
[qsv](/getting-started/from-qsv).
