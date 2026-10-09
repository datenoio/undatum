# Change: Add a Data Quality Report Command

## Why
Profiling (`stats`), schema inference (`schema`) and rule validation (`validate`) exist as separate
commands with separate outputs. Data teams need one artifact per dataset that answers "is this file
fit for use?" and one exit code CI can act on (a data contract). This also fulfils the deferred
`add-advanced-quality-monitoring` item of `add-undatum-improvement-roadmap` (task 4.7).

## What Changes
- New command `undatum quality <file> [--rules rules.yml] [--schema expected.json]
  [--thresholds quality.yml] [--format-out html|md|json] [-o report.html]`.
- The report combines: row and column counts, inferred vs expected schema, per-field null rate,
  distinct count, top values and type conformance (from `stats`), rule violations by severity
  (from `validate`), and a pass/fail verdict per threshold.
- Thresholds file: e.g. `max_null_rate: {email: 0.01}`, `min_rows: 1000`,
  `max_error_violations: 0`, `schema: strict|additive`.
- Exit code 0 when all thresholds pass, 1 when any fails (distinct from usage errors, which keep
  the error-handling codes) — documented for CI use.
- Single pass over the data where possible (DuckDB for profiling when the format allows).

## Impact
- Affected specs: `data-validation`
- Affected code: new `undatum/cmds/quality.py`, report templates in `undatum/templates/`,
  `undatum/cli/data_commands.py` (or its successor), docs page and cookbook entry
- Depends on: `fix-cli-exit-codes`; benefits from `add-validation-rule-library`
