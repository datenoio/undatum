## Context
Options are declared inline in each Typer command in `undatum/cli/data_commands.py`
(3 692 lines), so names drift. A few shared `Annotated` aliases already exist (`TableNameOpt`,
`FlattenNestedOpt`, `OnErrorOpt`); this change extends that pattern to every common option.

## Decisions

| Concept | Canonical | Short | Hidden aliases (warn) |
| --- | --- | --- | --- |
| Input format | `--format-in` | `-F` | `--filetype` |
| Output serialization | `--format-out` | `-O` | `--output-format`, `--outtype`, `--format` (where it means serialization) |
| Output destination | `--output` | `-o` | positional output in `convert` stays valid |
| Row limit | `--limit` | `-n` | `--n`, `--objects-limit` |
| Field list | `--fields` | `-f` | — |
| CSV delimiter | `--delimiter` | `-d` | — |
| Engine | `--engine auto\|duckdb\|python` | `-e` | value `iterable` |
| AI options outside `ai` | `--ai-provider`, `--ai-model`, `--ai-base-url` | — | — |
| AI options inside `ai` | `--provider`, `--model`, `--base-url` | — | `--ai-*` accepted |

- `--format` remains canonical only where it selects a dialect rather than a serialization
  (`schema --format cerberus|jsonschema|avro|parquet`).
- Alias handling: the root group rewrites deprecated spellings before parsing and emits one warning
  per spelling to stderr: `Option --filetype is deprecated; use --format-in (removal in 2.0)`.
  Conventions are applied to the built Click tree (`undatum/cli/conventions.py`) rather than to each
  declaration, so plugin commands follow them too.
- Alternatives considered: renaming without aliases (breaks scripts and agents), or keeping
  everything (does not fix discoverability).

## Risks / Trade-offs
- Short-flag collisions with existing per-command flags → the Click-tree test checks uniqueness
  per command.
- Plugins may register old names → plugin docs get the vocabulary table; warnings are not fatal.

## Migration Plan
1. Introduce shared types and aliases (v1.8). 2. Update docs and recipes to canonical names.
3. Remove aliases in v2.0.
