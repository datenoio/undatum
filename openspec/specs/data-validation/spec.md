# data-validation Specification

## Purpose
Check data against rules and report its quality: the validate command and its rule file format, severities and violation reports, the built-in rule library, cross-file references, safe rule expressions, the quality report with thresholds, and machine-readable results.
## Requirements
### Requirement: Validation Command
The system SHALL provide comprehensive data validation capabilities with support for rule-based validation.

#### Scenario: Validate with rule file
- **WHEN** user runs `undatum validate data.csv --rules validation-rules.yml`
- **THEN** the system SHALL parse the rule file
- **AND** apply all defined rules to the dataset
- **AND** report violations grouped by severity (errors, warnings, info)
- **AND** provide summary statistics

#### Scenario: Validate with CLI options (backward compatibility)
- **WHEN** user runs `undatum validate data.csv --fields email --rule email`
- **THEN** the system SHALL behave as before
- **AND** apply the specified rule to the specified field
- **AND** maintain existing output format

#### Scenario: Violation summary reporting
- **WHEN** user runs `undatum validate data.csv --rules rules.yml`
- **THEN** the system SHALL display:
  - Total records processed
  - Violations by severity (errors, warnings, info)
  - Violations by rule type
  - Violations by field
  - Pass/fail rate

### Requirement: Rule Definition Format
Validation rules SHALL be defined in YAML or JSON format with support for multiple rule types.

#### Scenario: Field-level rules
- **WHEN** user creates a rule file with field-level rules:
  ```yaml
  rules:
    - field: email
      required: true
      type: string
      format: email
      severity: error
    
    - field: age
      type: number
      min: 0
      max: 120
      severity: warning
  ```
- **THEN** the system SHALL validate each field according to its rules
- **AND** report violations with appropriate severity

#### Scenario: Cross-field rules
- **WHEN** user creates a rule file with cross-field validation:
  ```yaml
  rules:
    - type: cross-field
      condition: "start_date <= end_date"
      fields: [start_date, end_date]
      severity: error
  ```
- **THEN** the system SHALL validate the condition across multiple fields
- **AND** report violations when the condition fails

### Requirement: Severity Levels
Validation rules SHALL support different severity levels.

#### Scenario: Hard errors
- **WHEN** a rule with `severity: error` is violated
- **THEN** the system SHALL treat it as a hard error
- **AND** count it in error statistics
- **AND** include it in error reports

#### Scenario: Soft warnings
- **WHEN** a rule with `severity: warning` is violated
- **THEN** the system SHALL treat it as a warning
- **AND** count it separately from errors
- **AND** allow validation to continue

### Requirement: Violation Reporting
The validation command SHALL provide comprehensive violation reporting.

#### Scenario: Summary report
- **WHEN** validation completes
- **THEN** the system SHALL display:
  - Total records: 1000
  - Errors: 15 (1.5%)
  - Warnings: 42 (4.2%)
  - Passed: 943 (94.3%)

#### Scenario: Detailed violation report
- **WHEN** user requests detailed report with `--violation-report violations.json`
- **THEN** the system SHALL output:
  - Record-level violation details
  - Field values that failed validation
  - Rule descriptions
  - Severity levels

### Requirement: Rule Types
The system SHALL support multiple rule types for comprehensive validation.

#### Scenario: Required field validation
- **WHEN** a field has `required: true`
- **THEN** the system SHALL report violations for missing/null values

#### Scenario: Type validation
- **WHEN** a field has `type: number`
- **THEN** the system SHALL validate that values are numeric
- **AND** report violations for non-numeric values

#### Scenario: Format validation
- **WHEN** a field has `format: email`
- **THEN** the system SHALL validate email format
- **AND** report violations for invalid formats

#### Scenario: Range validation
- **WHEN** a field has `min: 0` and `max: 100`
- **THEN** the system SHALL validate values are within range
- **AND** report violations for out-of-range values

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

