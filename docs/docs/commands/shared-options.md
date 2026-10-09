---
title: "Shared CLI options"
description: "Flags that appear on many undatum commands"
---
# Shared CLI options

Many file commands accept the same reader and error-policy flags. `undatum <command> --help` is the live list for a given command; this page explains the ones that show up repeatedly.

See also [Basic usage](/getting-started/basic-usage) for filter syntax, encoding, and compression.

## Option names

Every command uses the same name for the same idea:

| Concept | Option | Short |
| --- | --- | --- |
| Output file | `--output` | `-o` |
| Input format override | `--format-in` | `-F` |
| Output format | `--format-out` | `-O` |
| Number of rows | `--limit` | `-n` |
| Field list | `--fields` | `-f` |
| CSV delimiter | `--delimiter` | `-d` |
| Processing engine (`auto`, `duckdb`, `python`) | `--engine` | `-e` |

`--format` is kept only where it picks a dialect rather than a file format (`schema --format cerberus`).
Older spellings still work and print a deprecation warning; they will be removed in 2.0:

| Old | Use instead |
| --- | --- |
| `--filetype` | `--format-in` |
| `--outtype`, `--output-format` | `--format-out` |
| `--format` on `doc`, `sql`, `plot`, `sniff`, `diff`, `ai doc`, `api openapi`, `pipeline doc` | `--format-out` |
| `--n`, `--objects-limit` | `--limit` |
| `--engine iterable` | `--engine python` |
| `--ai-provider`, `--ai-model`, `--ai-base-url` inside `undatum ai` | `--provider`, `--model`, `--base-url` |

Duplicate commands are hidden from `--help` and warn when used: `profile` (use `stats`),
`document` (use `doc`), `ingest` (use `db load`), `scheme` (use `schema --format cerberus`).

Global flags go before the command: `-v` (progress messages), `-vv` (debug), `-q` (errors only).
A successful command prints nothing on stderr by default.

## Nested records

Unfold nested dict / array-of-dict fields onto dotted paths before the command runs:

```bash
undatum select --fields name,capital_city.lat --flatten-nested nested.jsonl
undatum stats nested.jsonl --flatten-nested --max-nested-depth 2 --no-keep-nested-parents
```

| Flag | Meaning |
|------|---------|
| `--flatten-nested` | Unfold nested objects onto dotted field names |
| `--max-nested-depth N` | Cap unfold depth (engine default is 5) |
| `--keep-nested-parents` / `--no-keep-nested-parents` | Keep or drop parent dict/array fields alongside dotted children. Default is **on** for most row commands and `stats`; **off** for `schema`. |

## Parse errors

| Flag | Meaning |
|------|---------|
| `--on-error raise\|skip\|warn` | What to do with a malformed row (default: `raise`). `skip` and `warn` force the iterable engine instead of DuckDB. |
| `--error-log PATH` | Append skipped or warned parse errors as JSONL (use with `skip` or `warn`) |

```bash
undatum convert messy.csv out.jsonl --on-error skip --error-log errors.jsonl
```

## Tables, sheets, and CSV dialect

| Flag | Meaning |
|------|---------|
| `--table` / `--sheet` | Named table or Excel sheet. Two-file commands also take `--table2`. `ingest` / `db load` use `--source-table`. |
| `--start-page N` | 0-based sheet index (Excel) |
| `--delimiter` | CSV delimiter. Auto-detected (comma, semicolon, tab, pipe) when omitted on commands that leave it unset. Some commands default to `,` instead of auto-detect (`fmt`, `flatten`, `apply`, `split`). |
| `--quotechar` | CSV quote character (iterabledata default `"`). Also `defaults.quotechar` / `UNDATUM_QUOTECHAR`. |
| `--encoding` | Text encoding. Auto-detected when the command leaves it unset; several commands default to `utf8` (`convert`, `flatten`, `apply`, `split`). |
| `--format-in` | Override input format on most commands (`csv`, `jsonl`, `xml`, …). **Exceptions:** `sort`, `dedup`, `reverse`, `slice`, and `count` use `--format-in` instead. |
| `--tagname` | XML element that contains one record |
| `--trust` | Acknowledge pickle deserialization risk (convert, stats, schema, select, head, and others that can read pickle) |

List sheets before converting:

```bash
undatum formats tables workbook.xlsx
undatum convert workbook.xlsx out.jsonl --table Sheet2
```

## Row filters

Commands that subset rows take `--filter` (alias `--filter-expr`) with a comparison expression. The same expression is pushed to DuckDB `WHERE` when possible.

```bash
undatum select --fields name,email --filter '`status` == "active"' data.jsonl
undatum frequency --fields city --filter 'age >= 30' data.jsonl
```

`--filter` does not support `LIKE`, `IN`, or regex. Use [`sql`](/commands/sql) for those. Full syntax: [Basic usage](/getting-started/basic-usage).

`--where` (on `select`, `search`, `head`, `sample`, `count` and `convert`) takes a full SQL
condition evaluated by DuckDB, including `LIKE`, `IN`, functions and dates; `--add
"name = expression"` (on `select` and `convert`) adds computed columns. See the
[cookbook](/getting-started/cookbook#filter-and-compute-with-sql-expressions).

```bash
undatum select data.csv --where "city IN ('Berlin', 'Paris') AND amount > 50" --fields name,amount
```

`convert` takes two positional paths and `--flatten-data` (not `--flatten-nested`). Most other write commands take `--output PATH` rather than a trailing positional file.

## Output formats

`--output` writes the format implied by the file extension: any writable format from
`undatum formats list --writable` (CSV, TSV, JSON, JSON Lines, Parquet, Avro, BSON, YAML, …),
optionally compressed (`out.csv.gz`, `out.jsonl.zst`). Output is written to a temporary file
and renamed on success, so a failed command leaves no partial file. A format that cannot be
written (for example `.xlsx`) fails with exit code 1 before anything is created.

```bash
undatum rename data.csv --map "a:x" --output out.parquet
undatum head data.jsonl --limit 100 --output sample.csv.gz
```

## Cloud URIs

Input and output paths may be `s3://`, `gs://` / `gcs://`, or `az://` / `abfs://` / `abfss://` when the matching extra is installed. See [Cloud storage](/integrations/cloud).
