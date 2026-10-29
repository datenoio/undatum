---
title: "Coming from csvkit"
description: "csvkit commands and their undatum equivalents"
---
# Coming from csvkit

undatum covers the csvkit workflow (cut, grep, sort, join, stack, statistics, conversion and
SQL), and runs it on JSON Lines, Parquet, Excel, XML and the other formats it reads, not only
CSV. This page maps csvkit 2.x commands to undatum.

## What works differently

- **Columns by name.** Columns are chosen by name with `--fields`; csvkit's `-c` also takes
  column numbers.
- **Values stay text.** undatum reads CSV values as text, as they are in the file; csvkit
  guesses types with agate. Sort numbers with `--numeric`, and compare numbers in `--where`,
  which types text automatically.
- **Output format.** Records go to stdout in the input's format, or to `--output` in the
  format of its extension (`--format-out` overrides it). csvkit always writes CSV.
- **Two engines.** Commands with `--engine` run in DuckDB when it reads the input, and in
  Python otherwise, with the same results.
- **JSON results.** `count`, `headers`, `stats`, `schema`, `validate` and the other
  informational commands print a versioned JSON document with `--json`.

## Command map

| csvkit | undatum | Notes |
|---|---|---|
| `csvcut -c name,city` | `undatum select --fields name,city` | Names, in the order given |
| `csvcut -C email` | `undatum select --fields ...` | List the fields to keep |
| `csvcut -n` | `undatum headers` | |
| `csvgrep -c city -m Berlin` | `undatum search --fields city --pattern Berlin` | `--pattern` is a regular expression |
| `csvgrep -c city -r '^B'` | `undatum search --fields city --pattern '^B'` | `--ignore-case` for case-insensitive matches |
| `csvgrep -i` | `undatum select --where "city <> 'Berlin'"` | Any DuckDB SQL condition |
| `csvsort -c amount -r` | `undatum sort --by amount --numeric amount --desc` | Text order unless the field is in `--numeric` |
| `csvjoin -c id a.csv b.csv` | `undatum join a.csv b.csv --on id` | Two files; the key has the same name in both |
| `csvjoin --left` / `--right` / `--outer` | `undatum join --type left` / `right` / `full` | |
| `csvstack a.csv b.csv` | `undatum cat a.csv b.csv` | `--mode columns` puts the files side by side |
| `csvlook` | `undatum table` | The first 20 rows; `-n` for more |
| `csvstat` | `undatum stats` | `--json` for a `undatum.stats/1` document |
| `csvstat --freq -c city` | `undatum frequency --fields city` | |
| `csvstat --count` | `undatum count` | `--where` counts the matching records |
| `csvjson data.csv` | `undatum convert data.csv data.json` | |
| `csvjson --stream` | `undatum convert data.csv data.jsonl` | |
| `in2csv workbook.xlsx --sheet Cities` | `undatum convert workbook.xlsx cities.csv --table Cities` | xls, xlsx, xlsm, xlsb and ods, with typed values |
| `in2csv -n workbook.xlsx` | `undatum formats tables workbook.xlsx` | |
| `in2csv data.json` | `undatum convert data.json data.csv` | Also GeoJSON, DBF, fixed width and the other readable formats |
| `csvformat -D ';'` | `undatum fmt --delimiter ';'` | `--quote`, `--escape`, `--line-ending` |
| `csvformat -T` | `undatum convert data.csv data.tsv` | |
| `csvclean` | `undatum fixlengths` | Pads short rows or truncates long ones (`--strategy`) |
| `csvsql --query "..." data.csv` | `undatum sql "..." data.csv` | DuckDB SQL; the table is `data`, or the file name without its extension |
| `csvsql --db URL --insert data.csv` | `undatum db load data.csv --db URL --table NAME --create-table` | PostgreSQL, MySQL, SQL Server, ClickHouse, SQLite, DuckDB, MongoDB, Elasticsearch |
| `sql2csv --db URL --query "..."` | `undatum db query "..." --db URL` | |
| `csvpy data.csv` | `Dataset.read("data.csv")` | The [Python SDK](/integrations/sdk) |
| none | `undatum head`, `undatum tail`, `undatum slice` | First, last or a range of records |

## Side by side

```bash
# csvcut -c name,city data.csv
undatum select data.csv --fields name,city

# csvgrep -c city -m Berlin data.csv
undatum search data.csv --fields city --pattern Berlin

# csvgrep -c amount ... cannot compare numbers; --where can
undatum select data.csv --where "amount > 100 AND city = 'Berlin'"

# csvsort -c amount -r data.csv
undatum sort data.csv --by amount --numeric amount --desc

# csvjoin -c id --left people.csv orders.csv
undatum join people.csv orders.csv --on id --type left

# csvstack people.csv orders.csv
undatum cat people.csv orders.csv

# csvlook data.csv
undatum table data.csv --fields name,city

# csvstat data.csv
undatum stats data.csv

# csvjson data.csv > data.json
undatum convert data.csv data.json

# in2csv --sheet Cities workbook.xlsx > cities.csv
undatum convert workbook.xlsx cities.csv --table Cities

# csvsql --query "SELECT city, COUNT(*) AS n FROM data GROUP BY city" data.csv
undatum sql "SELECT city, COUNT(*) AS n FROM data GROUP BY city" data.csv
```

The same commands read other formats as they are:

```bash
undatum select data.parquet --fields name,city
undatum search data.jsonl --fields city --pattern Berlin
undatum stats data.jsonl.gz
```

## What undatum adds

- **Formats:** JSON Lines, Parquet, ORC, Avro, Excel, XML, BSON, geospatial and scientific
  formats, and compressed files (see [formats](/formats)).
- **Data quality:** rule files ([`validate`](/commands/validate)), quality reports with
  thresholds ([`quality`](/commands/quality)), schema inference and drift
  ([`schema`](/commands/schema), [`schema-drift`](/commands/schema-drift)), and file
  comparison ([`diff`](/commands/diff)).
- **Record operations csvkit lacks:** [`dedup`](/commands/dedup),
  [`sample`](/commands/sample), [`split`](/commands/split), [`fill`](/commands/fill),
  [`explode`](/commands/explode), [`mask`](/commands/mask) and
  [`transpose`](/commands/transpose).
- **Agents and Python:** an [MCP server](/integrations/mcp), the
  [Python SDK](/integrations/sdk) and the CLI as data ([`commands`](/commands/commands)).

See also [Coming from qsv](/getting-started/from-qsv) and the
[cheat sheet](/getting-started/cheat-sheet).
