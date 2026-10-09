---
title: "Cookbook"
description: "Pick a role and goal, then follow verified undatum commands"
---
# Cookbook

undatum covers many workflows. This page is a task-oriented index: find the row
that sounds like you, then follow the linked reference sections. If you are
completely new, do the [five-minute quickstart](/getting-started/quick-start) first.

| You are a… | You want to… | Start with |
|------------|--------------|------------|
| [Data analyst](/use-cases/sql-and-analytics) | Inspect unfamiliar files and answer questions without writing a program | `table`, `tui`, `web`, `stats`, `frequency`, `sql`, `plot` |
| [Data engineer](/use-cases/data-pipelines) | Build repeatable, streaming transformations across formats, databases, and object storage | `convert`, `dedup`, `db dump` / `db load`, `pipeline` |
| [Data steward](/use-cases/quality-and-packaging) | Assess quality, encode reusable rules, and produce evidence before data is released | `analyze`, `validate`, `diff`, `schema` |
| [Open-data publisher](/use-cases/quality-and-packaging) | Publish documented, portable, standards-friendly datasets | `package`, `doc`, `mask`, `validate` |
| [Application developer](/integrations/sdk) | Embed data preparation in Python or expose a dataset through a read-only API | Python `Dataset` SDK, `api` |
| [Researcher / journalist](/use-cases/format-conversion) | Turn awkward public files and documents into analysis-ready, shareable data | `extract`, `sniff`, `convert`, `doc` |
| [Operations / security analyst](/commands/search) | Search large event exports, reduce sensitive data, and create focused incident extracts | `search`, `select`, `sample`, `mask` |
| [AI / automation builder](/use-cases/agents-and-mcp) | Give agents controlled dataset tools or add AI assistance to documentation | `mcp`, `ai doc`, LangChain tools |
| [Plugin author](/integrations/plugins) | Add domain-specific commands, connectors, or transforms without a fork | `plugins`, entry points |

All commands below are also available via the shorter `data` alias
(`data convert …` is identical to `undatum convert …`).


## Shell pipelines

Every record command reads `-` as standard input and writes to standard output when
`--output` is omitted. See [Basic usage](/getting-started/basic-usage#pipelines-standard-input-and-output)
for how formats are chosen.

```bash
# Top 10 rows by amount, still CSV
cat sales.csv | undatum sort - --by amount --numeric amount --desc | undatum head - -n 10

# Unique error events from a compressed log export
gzip -dc events.jsonl.gz | undatum search - --pattern ERROR --fields level | undatum dedup -

# Write Parquet to a pipe (refused on a terminal)
undatum head big.csv -n 100000 -O parquet > head.parquet
```

```bash norun
# Random sample of a remote file as JSON Lines
curl -s https://example.org/export.csv | undatum sample - --limit 100 -O jsonl
```

## Filter and compute with SQL expressions

`--where` keeps the rows for which a SQL condition is true; `--add` adds a computed column.
DuckDB evaluates both, and text columns are typed automatically (numbers, dates, booleans),
so `amount > 100` works on CSV. Values you do not compute keep their original text.

```bash
undatum select data.csv --where "amount > 100 AND city = 'Berlin'"
undatum convert data.csv totals.parquet --add "total = price * quantity"
undatum count data.jsonl --where "date >= DATE '2024-05-01'"
undatum select data.csv --where "lower(status) = 'active'" --add "big = amount > 200"
```

`--where` works on `select`, `search`, `head`, `sample`, `count` and `convert`; `--add` on
`select` and `convert`. Compared with [`undatum sql`](/commands/sql): `--where` keeps the
input's format and columns and fits into the command you already use; `sql` is for
grouping, joins and reshaping.

```bash
# Same rows, two ways
undatum select data.csv --where "amount > 100"
undatum sql "SELECT * FROM data WHERE TRY_CAST(amount AS DOUBLE) > 100" data.csv
```

A column where some values are not numbers stays text; cast it in the expression, for
example `TRY_CAST(price AS DOUBLE) > 10`. Placeholders such as `n/a`, `null` and `-` count
as missing values.

## Detailed walkthroughs

- [Format conversion](/use-cases/format-conversion)
- [Data pipelines](/use-cases/data-pipelines)
- [Quality and packaging](/use-cases/quality-and-packaging)
- [SQL and analytics](/use-cases/sql-and-analytics)
- [Agents and MCP](/use-cases/agents-and-mcp)
