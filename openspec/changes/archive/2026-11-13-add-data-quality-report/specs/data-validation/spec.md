## ADDED Requirements

### Requirement: Data Quality Report Command
The system SHALL provide a `quality` command that produces one report combining profiling,
schema conformance and rule-validation results for a dataset, in HTML, Markdown or JSON.

#### Scenario: HTML report
- **WHEN** user runs `undatum quality data.csv --rules rules.yml -o report.html`
- **THEN** `report.html` contains row counts, per-field null rates and type conformance, schema
  differences and rule violations grouped by severity

#### Scenario: JSON report for automation
- **WHEN** user runs `undatum quality data.csv --format-out json`
- **THEN** stdout is a JSON document with `summary`, `fields`, `schema_check`, `violations` and `verdict`
  (`schema` holds the layout id `undatum.quality/1`, as in every JSON result)

### Requirement: Quality Thresholds and Exit Status
The `quality` command SHALL evaluate thresholds from a file and SHALL exit with code 0 when all
thresholds pass and code 1 when any threshold fails.

#### Scenario: Null-rate threshold exceeded
- **WHEN** thresholds set `max_null_rate.email: 0.01` and 5% of `email` values are empty
- **THEN** the report marks the threshold as failed
- **AND** the command exits with code 1
