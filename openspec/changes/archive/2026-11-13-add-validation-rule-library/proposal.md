# Change: Built-In Validation Rule Library

## Why
Only five built-in checks exist (`common.email`, `common.url`, `integer`, `ru.org.inn`,
`ru.org.ogrn` in `undatum/validate/`), plus `uuid` in the YAML engine. Common open-data and
analytics checks — dates, phone numbers, country and currency codes, IBAN, regex patterns,
uniqueness, references between files — must be written by hand. An unknown `format:` value is
logged as a warning and then treated as passing (`undatum/common/validation_rules.py`,
`_validate_format`), so a typo such as `format: emial` silently disables the check. Results are
printed for humans only.

## What Changes
- Rule library with documented names: `date` (with `formats`), `datetime`, `phone` (E.164 and
  national via `phonenumbers` in an optional extra), `country` (ISO 3166-1 alpha-2/alpha-3),
  `currency` (ISO 4217), `language` (ISO 639-1), `iban`, `uuid`, `pattern` (regex), `unique`,
  `not_null`, numeric `range`, `length`; existing Russian identifiers stay under `ru.*`.
- `undatum validate --list-rules` prints the catalogue with parameters.
- Unknown rule or format names are configuration errors (exit 2) listing the closest names.
- Cross-file reference rule: `references: {file: countries.csv, field: code}` streams the
  reference keys into a set (or DuckDB when large).
- Machine-readable results: `--format-out json|jsonl` with a stable schema (rule, field, severity,
  row index, value sample, message) and summary counts.

## Impact
- Affected specs: `data-validation`
- Affected code: `undatum/validate/`, `undatum/common/validation_rules.py`,
  `undatum/cmds/validator.py`, `pyproject.toml` (optional `phone` extra), docs
