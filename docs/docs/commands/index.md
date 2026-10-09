---
title: "CLI Reference"
description: "Index of undatum CLI commands"
slug: /commands
---

# CLI Reference

All commands are available as `undatum <command>` or the shorter `data` alias
(`data convert …` is identical to `undatum convert …`).

Use `undatum <command> --help` for the live flag list. Flags that appear on many
commands (`--format-in`/`--format-out`, `--limit`, `--where`, `--flatten-nested`, `--on-error`,
`--filter`, `--table`, `--quotechar`) are documented under
[Shared CLI options](/commands/shared-options). `-` as the input path reads standard input, and
informational commands print a versioned JSON document with `--json` — see
[JSON output](/commands/json-output). Exit codes are listed under
[troubleshooting](/getting-started/troubleshooting).

## Convert and I/O

| Command | Page |
|---------|------|
| `convert` | [`/commands/convert`](/commands/convert) |
| `repack` | [`/commands/repack`](/commands/repack) |
| `flatten` | [`/commands/flatten`](/commands/flatten) |
| `formats` | [`/commands/formats`](/commands/formats) |
| Shared flags | [`/commands/shared-options`](/commands/shared-options) |
| JSON output | [`/commands/json-output`](/commands/json-output) |

## Inspect

| Command | Page |
|---------|------|
| `analyze` | [`/commands/analyze`](/commands/analyze) |
| `headers` | [`/commands/headers`](/commands/headers) |
| `sniff` | [`/commands/sniff`](/commands/sniff) |
| `count` | [`/commands/count`](/commands/count) |
| `head` | [`/commands/head`](/commands/head) |
| `tail` | [`/commands/tail`](/commands/tail) |
| `table` | [`/commands/table`](/commands/table) |
| `stats` | [`/commands/stats`](/commands/stats) |
| `frequency` | [`/commands/frequency`](/commands/frequency) |
| `uniq` | [`/commands/uniq`](/commands/uniq) |

## Transform

| Command | Page |
|---------|------|
| `select` | [`/commands/select`](/commands/select) |
| `sort` | [`/commands/sort`](/commands/sort) |
| `sample` | [`/commands/sample`](/commands/sample) |
| `search` | [`/commands/search`](/commands/search) |
| `dedup` | [`/commands/dedup`](/commands/dedup) |
| `fill` | [`/commands/fill`](/commands/fill) |
| `rename` | [`/commands/rename`](/commands/rename) |
| `explode` | [`/commands/explode`](/commands/explode) |
| `replace` | [`/commands/replace`](/commands/replace) |
| `cat` | [`/commands/cat`](/commands/cat) |
| `join` | [`/commands/join`](/commands/join) |
| `diff` | [`/commands/diff`](/commands/diff) |
| `exclude` | [`/commands/exclude`](/commands/exclude) |
| `transpose` | [`/commands/transpose`](/commands/transpose) |
| `slice` | [`/commands/slice`](/commands/slice) |
| `fmt` | [`/commands/fmt`](/commands/fmt) |
| `split` | [`/commands/split`](/commands/split) |
| `enum` | [`/commands/enum`](/commands/enum) |
| `reverse` | [`/commands/reverse`](/commands/reverse) |
| `fixlengths` | [`/commands/fixlengths`](/commands/fixlengths) |
| `apply` | [`/commands/apply`](/commands/apply) |
| `mask` | [`/commands/mask`](/commands/mask) |

## Quality and documentation

| Command | Page |
|---------|------|
| `quality` | [`/commands/quality`](/commands/quality) |
| `validate` | [`/commands/validate`](/commands/validate) |
| Validation rules | [`/commands/validate-rules`](/commands/validate-rules) |
| `schema` | [`/commands/schema`](/commands/schema) |
| `schema-bulk` | [`/commands/schema-bulk`](/commands/schema-bulk) |
| `schema-drift` | [`/commands/schema-drift`](/commands/schema-drift) |
| `doc` | [`/commands/doc`](/commands/doc) |

## SQL and visualization

| Command | Page |
|---------|------|
| `sql` | [`/commands/sql`](/commands/sql) |
| `plot` | [`/commands/plot`](/commands/plot) |

## Extract

| Command | Page |
|---------|------|
| `extract` | [`/commands/extract`](/commands/extract) |

## Packaging and pipelines

| Command | Page |
|---------|------|
| `package` | [`/commands/package`](/commands/package) |
| `pipeline` | [`/commands/pipeline`](/commands/pipeline) |
| `examples` | [`/commands/examples`](/commands/examples) |

## Databases

| Command | Page |
|---------|------|
| `db` | [`/commands/db`](/commands/db) |

## Interactive and API

| Command | Page |
|---------|------|
| `tui` | [`/commands/tui`](/commands/tui) |
| `web` | [`/commands/web`](/commands/web) |
| `api` | [`/commands/api`](/commands/api) |

## AI and agents

| Command | Page |
|---------|------|
| `ai` | [`/commands/ai`](/commands/ai) |
| `mcp` | [`/commands/mcp`](/commands/mcp) |

## Extensibility

| Command | Page |
|---------|------|
| `plugins` | [`/commands/plugins`](/commands/plugins) |
| `config` | [`/commands/config`](/commands/config) |
| `migrate-script` | [`/commands/migrate-script`](/commands/migrate-script) |

## Deprecated commands

These keep working with a warning on stderr and are removed in 2.0; they are hidden from
`--help`. [`migrate-script`](/commands/migrate-script) rewrites them in scripts, and the
[migration guide](/getting-started/migrating-to-2) lists every change.

| Command | Use instead |
|---------|-------------|
| `profile` | [`stats`](/commands/stats) |
| `document` | [`doc`](/commands/doc) |
| `scheme` | [`schema --format cerberus`](/commands/schema) |
| `ingest` | [`db load`](/commands/db) — see [`ingest`](/commands/ingest) |
