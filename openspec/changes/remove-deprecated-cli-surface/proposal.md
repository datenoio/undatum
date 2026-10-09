# Change: Remove Deprecated Commands and Option Aliases in v2.0

## Why
`update-cli-option-conventions` keeps old option names and duplicate commands as hidden aliases
with deprecation warnings during v1.8–v1.x. A major release should remove them so help, docs and
agent tool schemas describe one surface.

## What Changes
- **BREAKING**: remove the `scheme` command (use `schema --format cerberus`).
- **BREAKING**: remove hidden command aliases `profile`, `document`, `ingest`.
- **BREAKING**: remove deprecated option aliases (`--filetype`, `--outtype`, `--output-format`,
  serialization-meaning `--format`, `--n`, `--objects-limit`, engine value `iterable`).
- **BREAKING**: remove the legacy `--autodoc` flag only if issues and discussions show that users
  have moved to `ai doc`; otherwise keep it as a documented alias of `ai doc`.
- Publish a migration guide with a mechanical rewrite table, and a `undatum migrate-script`
  helper that rewrites shell scripts and pipeline YAML to canonical names.

## Impact
- Affected specs: `data-processing`, `cli-conventions`
- Affected code: `undatum/cli/`, alias tables, docs, recipes, pipeline templates
- Depends on: `update-cli-option-conventions` shipped for at least two minor releases
