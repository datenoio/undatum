---
title: "Best practices"
description: "Practical defaults for conversion, validation, and pipelines"
---
# Best practices

## Convert and store

- Prefer **Parquet** or **JSON Lines** for large or nested data. Avoid in-memory JSON arrays.
- Use `--low-memory` on multi-GB `convert`, `sort`, and `dedup`. See [performance](/getting-started/performance).
- Inspect the live catalog before choosing an output: `undatum formats list --writable`.
- Pass `--on-error skip` (and `--error-log`) when a few malformed rows should not abort a job.

## Validate before you publish

- Encode expectations in a rules file and run `undatum validate --rules rules.yml`; the
  [rule library](/commands/validate-rules) covers dates, phone numbers, ISO codes, IBAN,
  uniqueness and references to other files.
- Gate deliveries with [`undatum quality`](/commands/quality) and a thresholds file: it exits
  with 1 when a threshold fails.
- Catch schema changes before they break a load: `undatum schema-drift NEW --baseline schema.json --fail-on removed,type`.
- Pair validation with `analyze` / `stats` and `package validate`.
- For schema-only checks, use `undatum schema --validate`; keep `validate` for rule packs.

## Query and transform

- Use `--where` SQL conditions (`select`, `search`, `head`, `sample`, `count`, `convert`) for
  subsets and `--add` for computed columns; use [`sql`](/commands/sql) for joins and
  aggregations.
- Apply filters early (`--where`, `select --filter`, `search`) to cut volume before heavier steps.
- Keep the default `--engine auto`: it uses DuckDB on CSV/TSV/JSON/JSON Lines/Parquet.
- Chain commands with `-` (standard input) instead of temporary files.

## Pipelines and agents

- Validate pipeline YAML with `undatum pipeline validate` before `run`.
- Give agents [`mcp serve`](/integrations/mcp) rather than unconstrained shell access.
- Keep core verbs (`convert`, `stats`, `validate`, `select`) stable in scripts; check `CHANGELOG.md` before pinning flags.
- Parse `--json` output (it carries a versioned `schema` id) rather than text output, and rely
  on the documented exit codes.
- Run `undatum migrate-script --check` on your scripts in CI to catch deprecated spellings
  before 2.0 removes them.

## Configuration

Put shared defaults in `undatum.yaml` or `~/.undatum/config.yaml`, then inspect with `undatum config show`. See [config](/commands/config).
