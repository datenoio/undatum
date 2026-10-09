---
title: "Migrating to 2.0"
description: "Deprecated commands and options, their replacements, and how to update scripts"
---
# Migrating to 2.0

The next releases unify undatum's command-line vocabulary. Old command and option names
keep working with a warning on stderr until 2.0, which removes them:

```text
Warning: Option --filetype is deprecated; use --format-in (removal in 2.0) [undatum count]
```

`undatum migrate-script` rewrites scripts, Makefiles, CI files and pipeline YAML for you:

```bash norun
undatum migrate-script scripts/ pipelines/            # show the diff
undatum migrate-script scripts/ pipelines/ --write    # apply it
undatum migrate-script . --check                      # CI: fail while anything is left
```

## Commands

<!-- migrate-script: ignore -->

| Deprecated | Use instead | Rewritten automatically |
|------------|-------------|-------------------------|
| `undatum profile FILE` | `undatum stats FILE` | yes |
| `undatum document FILE` | `undatum doc FILE` | yes |
| `undatum scheme FILE` | `undatum schema FILE --format cerberus` | yes (`--stype X` → `--format X`) |
| `undatum ingest FILE URI DB TABLE` | `undatum db load FILE --db URI --table TABLE` | no, see below |

`schema` has no `--delimiter`, `--encoding`, `--format-in` or `--zipfile`: the delimiter
and encoding are detected, and ZIP archives are read directly. `migrate-script` lists
`scheme` calls that use them.

### `ingest` → `db load`

`db load` takes the database in the URI and the table (or collection, or index) as
`--table`:

| `ingest` | `db load` |
|----------|-----------|
| `ingest data.jsonl mongodb://localhost:27017 mydb people` | `db load data.jsonl --db mongodb://localhost:27017/mydb --table people` |
| `ingest data.csv postgresql://u:p@host:5432/mydb mydb events --dbtype postgresql` | `db load data.csv --db postgresql://u:p@host:5432/mydb --table events` |
| `ingest data.csv mysql://u:p@host/mydb mydb events --dbtype mysql` | `db load data.csv --db mysql://u:p@host/mydb --table events` |
| `ingest data.csv duckdb:///data.duckdb main events --dbtype duckdb` | `db load data.csv --db duckdb:///data.duckdb --table events` |
| `ingest data.csv sqlite:///data.db main events --dbtype sqlite` | `db load data.csv --db sqlite:///data.db --table events` |
| `ingest docs.jsonl https://host:9200 _ myindex --dbtype elasticsearch` | `db load docs.jsonl --db elasticsearch://host:9200 --table myindex` |

| `ingest` option | `db load` option |
|-----------------|------------------|
| `--dbtype` | the URI scheme |
| `--drop` | `--mode replace` |
| `--mode`, `--create-table`, `--upsert-key` | the same |
| `--api-key`, `--doc-id`, `--ca-cert`, `--insecure`, `--es-pipeline` | the same |
| `--batch`, `--totals`, `--skip`, `--timeout` | not available in `db load` |

In pipelines, replace `command: ingest` with `command: db load` (see
[pipeline database steps](/commands/pipeline#database-steps)):

```yaml norun
  - name: load
    command: db load
    args:
      input: $clean
      db: postgresql://user:pass@localhost:5432/mydb
      table: events
      create_table: true
```

## Options

| Deprecated | Use instead | Commands that accept the old spelling |
|------------|-------------|---------------------------------------|
| `--filetype` | `--format-in` / `-F` | `count`, `dedup`, `frequency`, `reverse`, `slice`, `sort`, `uniq` |
| `--outtype` | `--format-out` / `-O` | `analyze`, `schema`, `schema-bulk` |
| `--output-format` | `--format-out` / `-O` | `db query`, `diff`, `extract`, `validate` |
| `--format` (output serialization) | `--format-out` / `-O` | `ai doc`, `api openapi`, `diff`, `doc`, `document`, `pipeline doc`, `plot`, `sniff`, `sql` |
| `--n` | `--limit` / `-n` | `head`, `sample`, `tail` |
| `--objects-limit` | `--limit` / `-n` | `analyze`, `package create`, `package add-resource` |
| `--engine iterable` | `--engine python` | every command with `--engine` |

`--format` keeps its meaning where it does not choose the output serialization, for example
`schema --format cerberus` (the schema dialect) or `convert` (no such option).

## Other changes in this release

These are not deprecations but change behaviour; the [CHANGELOG](https://github.com/datenoio/undatum/blob/master/CHANGELOG.md)
has the full list.

- Python 3.10 is the minimum version.
- Record commands print the input's text format on stdout (CSV in, CSV out); add
  `-O jsonl` for the previous JSON Lines output.
- `--delimiter` is auto-detected when omitted and describes the input only.
- JSON documents of informational commands carry a `schema` id (see
  [JSON output](/commands/json-output)); `formats list --json` is an object.
- `--autodoc` masks likely personal data in samples sent to remote AI providers
  (`--no-pii-mask-samples` turns this off).
- The SDK `Dataset` is lazy: transforms build a plan, terminal methods run it.
