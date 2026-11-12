# Change: Unify CLI Option Names and Canonical Commands

## Why
The CLI has 80 leaf commands with 1 101 options under 200 distinct names. One concept often has
several names:
- input format: `--format-in` (36 commands) vs `--filetype` (7: count, dedup, frequency, reverse,
  slice, sort, uniq);
- output format: `--format` (11), `--format-out` (10), `--output-format` (4), `--outtype` (3);
  `analyze` has both `--outtype` and `--format-out`, `diff` has `--format` and `--output-format`;
- engine values: `python` (10 commands) vs `iterable` (9), unvalidated;
- row limit: `--n` (head, sample, tail), `--limit` (headers, table, tui, web), `--objects-limit`;
- AI options: `--ai-provider/--ai-model` (7) vs `--provider/--model` (4 in `ai`);
- output destination: positional in `convert`, `--output` in 52 commands.
Only 4 short flags exist in the whole CLI (`-o` on 1 of 52 commands with `--output`). Duplicate
commands add confusion: `stats`/`profile`, `doc`/`document`, `ingest` vs `db load`, deprecated
`scheme`, `--autodoc` vs `ai doc`.

## What Changes
- Canonical option vocabulary (table in `design.md`) declared once as shared `Annotated` types in
  `undatum/cli/options.py` and used by every command.
- Old names stay as hidden aliases that print a deprecation warning; removal is scheduled for
  v2.0 (`remove-deprecated-cli-surface`).
- Short flags: `-o/--output`, `-n/--limit`, `-f/--fields`, `-d/--delimiter`, `-e/--engine`,
  `-F/--format-in`, `-O/--format-out` where the command has the option.
- `--engine` uses `click.Choice(["auto", "duckdb", "python"])` with `iterable` mapped to `python`.
- Canonical commands: `stats` (`profile` hidden alias), `doc` (`document` hidden alias),
  `db load` (`ingest` maps positional arguments to `--db/--table` and warns), `ai doc`
  (`--autodoc` keeps working and delegates to the same code path).
- A test walks the Click tree and fails on any non-canonical visible option name.

## Impact
- Affected specs: `cli-conventions` (new)
- Affected code: `undatum/cli/*.py`, `docs/docs/commands/*.md`, `docs/docs/commands/shared-options.md`
- Not breaking in v1.x: every old spelling keeps working with a warning
