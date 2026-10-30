---
title: "Coming from qsv"
description: "qsv commands and their undatum equivalents"
---
# Coming from qsv

Many undatum commands have the same names as qsv commands: `select`, `search`, `sort`,
`frequency`, `stats`, `dedup`, `join`, `slice`, `sample`, `split`, `fill`, `explode`, `enum`,
`exclude`, `cat`, `sniff`, `schema`, `validate`, `table`, `diff` and others. This page maps
qsv 27 commands and options to undatum.

## What works differently

- **Named options instead of positional arguments.** qsv passes columns and patterns as
  positional arguments (`qsv search -s city '^B'`, `qsv join id a.csv id b.csv`); undatum uses
  named options (`--fields`, `--pattern`, `--on`).
- **Columns by name.** qsv selections also take column numbers, ranges and regular
  expressions; undatum takes a comma-separated list of names.
- **Values stay text in CSV.** Sort numbers with `--numeric`; `--where` conditions (DuckDB
  SQL) type text automatically.
- **Order is kept.** `dedup` keeps the first record of each key in input order; `qsv dedup`
  sorts its output.
- **Formats beyond CSV.** The same commands read JSON Lines, Parquet, Excel, XML and the other
  formats undatum supports, and write the format of the `--output` extension.
- **No index files.** Commands with `--engine` run in DuckDB, which reads CSV in parallel
  without `qsv index`.
- **SQL dialect.** `undatum sql` runs DuckDB SQL; `qsv sqlp` runs Polars SQL.

## Command map

| qsv | undatum | Notes |
|---|---|---|
| `qsv select name,city` | `undatum select --fields name,city` | |
| `qsv headers` | `undatum headers` | |
| `qsv count` | `undatum count` | `--where` counts the matching records |
| `qsv search -s city '^B'` | `undatum search --fields city --pattern '^B'` | `-i` is `--ignore-case` |
| `qsv search -v -s city '^B'` | `undatum select --where "NOT regexp_matches(city, '^B')"` | Any DuckDB SQL condition |
| `qsv sort -s amount -N -R` | `undatum sort --by amount --numeric amount --desc` | |
| `qsv frequency -s city` | `undatum frequency --fields city` | Most frequent first |
| `qsv stats --everything` | `undatum stats` | `--json` for a `undatum.stats/1` document |
| `qsv dedup -s city` | `undatum dedup --key-fields city` | `--keep last` keeps the last record |
| `qsv join id a.csv id b.csv` | `undatum join a.csv b.csv --on id` | The key has the same name in both files |
| `qsv join --left` / `--right` / `--full` | `undatum join --type left` / `right` / `full` | |
| `qsv join --left-anti` / `qsv exclude id a.csv id b.csv` | `undatum exclude a.csv b.csv --on id` | |
| `qsv slice -s 10 -l 5` | `undatum slice --start 10 --end 14` | 0-based; `--end` is included |
| `qsv slice -i 3` | `undatum slice --indices 3` | `--indices` takes a list: `0,3,7` |
| `qsv sample 100` | `undatum sample -n 100` | `--percent` for a share of the records |
| `qsv split -s 1000 parts` | `undatum split --chunksize 1000 --dirname parts` | |
| `qsv partition city parts` | `undatum split --fields city --dirname parts` | One file per value |
| `qsv fixlengths` | `undatum fixlengths` | `--strategy pad` or `truncate` |
| `qsv fmt -t ';'` | `undatum fmt --delimiter ';'` | `--quote`, `--escape`, `--line-ending` |
| `qsv rename --pairwise name,full_name` | `undatum rename --map name:full_name` | `--pattern` and `--replacement` rename by regex; there is no positional mode |
| `qsv replace -s city Berlin BER` | `undatum replace --field city --pattern Berlin --replacement BER` | Add `--regex` for a regular expression |
| `qsv fill -v unknown tags` | `undatum fill --fields tags --value unknown` | `--strategy forward` fills from the previous record, as `qsv fill` does |
| `qsv explode tags ','` | `undatum explode --field tags --separator ,` | |
| `qsv enum -c row` | `undatum enum --field row` | `--start` sets the first number |
| `qsv enum --uuid4` | `undatum enum --type uuid` | |
| `qsv enum --constant x` | `undatum enum --type constant --value x` | |
| `qsv cat rows a.csv b.csv` | `undatum cat a.csv b.csv` | |
| `qsv cat columns a.csv b.csv` | `undatum cat a.csv b.csv --mode columns` | |
| `qsv transpose`, `qsv reverse` | `undatum transpose`, `undatum reverse` | |
| `qsv table` | `undatum table` | The first 20 rows; `-n` for more |
| `qsv flatten` | `undatum flatten` | One `field value` line per value |
| `qsv sqlp data.csv "SELECT ... FROM _t_1"` | `undatum sql "SELECT ... FROM data" data.csv` | Tables are named `data`, or after the file name without its extension |
| `qsv sniff` | `undatum sniff` | |
| `qsv schema` | `undatum schema --format jsonschema` | Also YAML, Cerberus, Avro and Parquet schemas |
| `qsv validate data.csv schema.json` | `undatum validate data.csv --rules rules.yml` | YAML rule files; `undatum schema --validate` checks rows against the inferred schema |
| `qsv diff -k 0 a.csv b.csv` | `undatum diff a.csv b.csv --key id` | Keys by name; `--json` for a report |
| `qsv tojsonl` | `undatum convert data.csv data.jsonl` | |
| `qsv to parquet dir data.csv` | `undatum convert data.csv data.parquet` | Any writable format, by extension |
| `qsv to sqlite` / `qsv to postgres` | `undatum db load data.csv --db URL --table NAME --create-table` | Also MySQL, SQL Server, ClickHouse, DuckDB, MongoDB, Elasticsearch |
| `qsv excel -s Cities workbook.xlsx` | `undatum convert workbook.xlsx cities.csv --table Cities` | xls, xlsx, xlsm, xlsb and ods, with typed values |
| `qsv excel --metadata c workbook.xlsx` | `undatum formats tables workbook.xlsx` | Sheet names |
| `qsv extsort`, `qsv extdedup` | `undatum sort`, `undatum dedup` | Spill to disk on their own above their memory limits |
| `qsv luau`, `qsv py`, `qsv apply` | `undatum select --add "total = price * quantity"`, `undatum apply` | SQL expressions, or a Python script per record |
| `qsv describegpt` | `undatum ai doc` | Dataset documentation with an LLM |
| `qsv index` | none | Not needed (see above) |
| `qsv fetch`, `qsv geocode` | none | |

## Side by side

```bash
# qsv select name,city data.csv
undatum select data.csv --fields name,city

# qsv search -s city '^B' data.csv
undatum search data.csv --fields city --pattern '^B'

# qsv sort -s amount -N -R data.csv
undatum sort data.csv --by amount --numeric amount --desc

# qsv frequency -s city data.csv
undatum frequency data.csv --fields city

# qsv dedup -s city data.csv
undatum dedup data.csv --key-fields city

# qsv join --left id people.csv id orders.csv
undatum join people.csv orders.csv --on id --type left

# qsv slice -s 2 -l 3 data.csv
undatum slice data.csv --start 2 --end 4

# qsv split -s 3 parts data.csv
undatum split data.csv --chunksize 3 --dirname parts

# qsv partition city by-city data.csv
undatum split data.csv --fields city --dirname by-city

# qsv enum --uuid4 data.csv
undatum enum data.csv --type uuid --field uuid

# qsv sqlp data.csv "SELECT city, COUNT(*) AS n FROM _t_1 GROUP BY city"
undatum sql "SELECT city, COUNT(*) AS n FROM data GROUP BY city" data.csv

# qsv to parquet out data.csv
undatum convert data.csv data.parquet

# qsv excel -s Cities workbook.xlsx
undatum convert workbook.xlsx cities.csv --table Cities
```

## What undatum adds

- **Formats:** JSON Lines, Parquet, ORC, Avro, XML, BSON, lakehouse tables, geospatial and
  scientific formats, and compressed files (see [formats](/formats)).
- **Data quality:** quality reports with thresholds for CI ([`quality`](/commands/quality)),
  schema drift across files ([`schema-drift`](/commands/schema-drift)) and Frictionless data
  packages ([`package`](/commands/package)).
- **Python:** the [Python SDK](/integrations/sdk) runs the same operations on files and
  DataFrames.
- **Agents:** a read-only [MCP server](/integrations/mcp) with a sandbox, and the CLI as data
  ([`commands`](/commands/commands)).

See also [Coming from csvkit](/getting-started/from-csvkit) and the
[cheat sheet](/getting-started/cheat-sheet).
