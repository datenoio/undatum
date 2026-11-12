# data-validation Specification

## Purpose
Check data against rules and report its quality: the built-in rule library, cross-file references, safe rule expressions, the quality report with thresholds, and machine-readable validation results.
## Requirements
### Requirement: Safe Rule Expression Evaluation
Cross-field rule conditions SHALL be evaluated by a restricted expression evaluator that supports
only comparisons, boolean and arithmetic operators, literals, field references and a documented
function set, and MUST NOT execute arbitrary Python.

#### Scenario: Supported condition
- **WHEN** a rule has `condition: "start_date <= end_date and amount > 0"`
- **THEN** the condition is evaluated for each record

#### Scenario: Code execution attempt rejected
- **WHEN** a rule has `condition: "().__class__.__bases__[0].__subclasses__()"`
- **THEN** validation stops with a rule syntax error naming the unsupported construct

#### Scenario: Field named like a keyword
- **WHEN** a dataset has a field named `or` and a rule references it
- **THEN** the field value is used and the expression is not corrupted

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

### Requirement: Built-In Rule Library
The validator SHALL provide documented built-in rules for dates, phone numbers, ISO country,
currency and language codes, IBAN, UUID, regex patterns, uniqueness, non-null, numeric ranges and
lengths, and SHALL list them with `undatum validate --list-rules`.

#### Scenario: Country code rule
- **WHEN** a rule file declares `field: country, format: country` and a record has `country: XX`
- **THEN** the record is reported as a violation of the `country` rule

#### Scenario: Rule catalogue
- **WHEN** user runs `undatum validate --list-rules`
- **THEN** every built-in rule is listed with its parameters

### Requirement: Unknown Rule Names Are Errors
A rule file that references an unknown rule or format name SHALL fail validation setup with a
configuration error instead of skipping the check.

#### Scenario: Misspelled format
- **WHEN** a rule file declares `format: emial`
- **THEN** the command exits with code 2 and suggests `email`

### Requirement: Cross-File Reference Rules
The validator SHALL support rules that require field values to exist in a field of another file.

#### Scenario: Unknown reference value
- **WHEN** a rule declares `references: {file: countries.csv, field: code}` for field `country`
- **AND** a record has a `country` value missing from `countries.csv`
- **THEN** the record is reported as a reference violation

### Requirement: Machine-Readable Validation Results
The `validate` command SHALL output violations and summary counts as JSON or JSON Lines with a
documented, stable schema when `--format-out json` or `--format-out jsonl` is given.

#### Scenario: JSON Lines violations
- **WHEN** user runs `undatum validate data.csv --rules rules.yml --format-out jsonl`
- **THEN** each output line is one violation with `rule`, `field`, `severity`, `row` and `message`

