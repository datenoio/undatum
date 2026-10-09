---
title: "Basic usage"
description: "Compression, filters, encoding, and date detection"
---
# Basic usage

The CLI entry points are `undatum` and the shorter `data` alias.

### Pipelines: standard input and output

Use `-` as the input path to read standard input, and leave out `--output` to write to
standard output. Commands chain like other Unix tools:

```bash
cat data.csv | undatum sort - --by amount --numeric amount | undatum head - -n 10
undatum search events.jsonl --pattern ERROR --fields level | undatum dedup -
```

```bash norun
curl -s https://example.org/export.csv.gz | undatum count -
```

- **Input format** is detected from the first bytes (CSV, TSV, JSON, JSON Lines, Parquet)
  together with `.gz`, `.zst`, `.bz2` and `.xz` compression. Pass `--format-in` (`-F`) when
  detection guesses wrong, for example `-F tsv`.
- **Output format** on stdout follows the input's text format — CSV in, CSV out; JSON Lines
  in, JSON Lines out. Binary or unknown inputs print JSON Lines. Override it with
  `--format-out` (`-O`): `undatum head data.csv -n 5 -O jsonl`.
- **Binary formats** (`-O parquet`, ...) are written to stdout only when it is redirected or
  piped; on a terminal the command fails and suggests `--output`.
- **Logs and progress** go to stderr, so they never mix with the data. Closing the pipe early
  (`undatum head big.csv -n 1000000 | head -1`) ends the command quietly with exit code 0.

### Working with Compressed Files

undatum can process files inside compressed containers (ZIP, GZ, BZ2, XZ, ZSTD) with minimal memory usage.

```bash
# Process file inside ZIP archive
undatum headers --format-in jsonl data.zip

# Process XZ compressed file
undatum uniq --fields country --format-in jsonl data.jsonl.xz
```

### Filtering Data

Filter rows with comparison expressions on commands that support `--filter` (`select`, `frequency`, `uniq`, `plot`, `validate`, `split`, and others). The same expression is pushed to DuckDB `WHERE` when possible, or evaluated in-process on the iterable path. For `LIKE`, `IN`, joins, and aggregations, use `undatum sql`.

```bash norun
# Filter by field value
undatum select --fields name,email --filter '`status` == "active"' data.jsonl

# Complex filters (AND/OR and &&/|| are both accepted)
undatum frequency --fields category --filter '`price` > 100 && `status` == "active"' data.jsonl

# DuckDB-accelerated select with SQL pushdown
undatum select --fields name,email --filter '`status` == "active"' --engine duckdb data.jsonl

# Unique values after a filter
undatum uniq --fields city --filter 'age >= 30' --engine duckdb data.jsonl

# Natural-language filter (translates to an expression; use --apply to run)
undatum ai filter "customers in California with orders over 1000" data.csv --apply
```

**Filter syntax:**
- Field names: `` `fieldname` `` (backticks optional for simple names)
- Strings: `"value"` or `'value'`
- Comparisons: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Booleans: `AND` / `OR` or `&&` / `||` (both work)

**DuckDB pushdown:** comparisons, `AND`/`OR`/`&&`/`||`, parentheses, and simple identifiers are translated to `WHERE`. The following are not supported on `--filter` (use `undatum sql` instead):
- `IN` lists and SQL `LIKE`
- Nested dotted fields (`user.name`)
- Regex / `match`

**Migrating from older filters:** `AND`/`OR` and `&&`/`||` both work. Prefer double-quoted strings. There is no `IN` operator; write `status == "active" || status == "pending"`. The experimental MistQL `undatum query` command is gone; use [`sql`](/commands/sql) or `select --filter`.

For ad-hoc SQL over files, use [`sql`](/commands/sql) or [`db query`](/commands/db) against a database URI.

### Custom Encoding and Delimiters

CSV/TSV delimiters (comma, semicolon, tab, pipe) are **auto-detected** when `--delimiter` is omitted. `--delimiter` describes the input; written CSV uses commas and TSV uses tabs. `convert`, `flatten`, `apply`, and `split` default `--encoding` to `utf8`; pass `--encoding` when the file is not UTF-8.

Override when needed:

```bash
undatum headers --encoding cp1251 --delimiter ";" data.csv
undatum convert --encoding utf-8 --delimiter "," data.csv data.jsonl
```

### Date Detection

Automatic date/datetime field detection:

```bash
undatum stats data.jsonl
# Date detection is on by default; disable with --no-checkdates
undatum stats --no-checkdates data.jsonl
```

This uses the `qddate` library to automatically identify and parse date fields.

See also: [CLI reference](/commands/), [shared CLI options](/commands/shared-options), [performance](/getting-started/performance).
