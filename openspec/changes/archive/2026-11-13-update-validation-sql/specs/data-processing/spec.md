## ADDED Requirements

### Requirement: Validation Rules in DuckDB
For CSV and TSV input, `validate --rules` and `quality --rules` SHALL run field rules made of
required, data type, references, unique, numeric range, length, enum and pattern checks as one
DuckDB query, and SHALL report the same violations (rule, field, severity, row, value, message,
order) as the Python rules. Rules with `format`, `custom` or a cross-field condition, patterns
whose meaning differs in RE2, and values only Python reads as numbers SHALL be checked by the
Python engine.

#### Scenario: Same violations
- **WHEN** a user runs `undatum validate data.csv --rules rules.yml` with `--engine python` and
  with `--engine duckdb`
- **THEN** both reports list the same violations in the same order

#### Scenario: Rule only Python checks
- **WHEN** a rule file contains a `format: email` rule
- **THEN** the records are checked by the Python engine
