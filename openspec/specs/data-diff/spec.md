# data-diff Specification

## Purpose
Compare two datasets (`undatum diff`) by key or whole-row equality and emit added, removed, and changed records.
## Requirements
### Requirement: Dataset diff command
The system SHALL provide a `diff` command that compares two input datasets and
reports differences across supported formats.

#### Scenario: Basic diff execution
- **WHEN** the user runs `undatum diff old.csv new.csv`
- **THEN** the system outputs a summary of differences

### Requirement: Key-based row matching and order handling
The system SHALL allow row matching by one or more key columns and SHALL support
an option to treat inputs as unordered sets.

#### Scenario: Key-based matching
- **WHEN** the user provides `--key id`
- **THEN** rows are matched by the specified key column

#### Scenario: Order-independent comparison
- **WHEN** the user provides `--ignore-order`
- **THEN** row order does not affect diff results

### Requirement: Difference categories
The system SHALL report added rows, removed rows, and changed rows (same key,
different values).

#### Scenario: Changed row detection
- **WHEN** a row with the same key has different field values
- **THEN** the row is reported as changed

### Requirement: Type-aware comparison controls
The system SHALL support numeric tolerance for float comparisons and
case-insensitive comparison for strings when explicitly enabled.

#### Scenario: Numeric tolerance
- **WHEN** the user provides `--numeric-tolerance 0.01`
- **THEN** numeric differences within tolerance are not reported as changes

#### Scenario: Case-insensitive comparison
- **WHEN** the user provides `--ignore-case`
- **THEN** string comparisons are case-insensitive

### Requirement: Output formats and destinations
The system SHALL always emit a summary count and SHALL support detailed output
in JSON, CSV, Markdown, or HTML with an optional output file path.

#### Scenario: Summary-only output
- **WHEN** the user runs `diff` without `--output-format`
- **THEN** a summary is written to standard output

#### Scenario: Detailed output to file
- **WHEN** the user provides `--output-format json` and `--output diff.json`
- **THEN** the system writes a detailed diff report to the specified file

### Requirement: CI thresholds and exit status
The system SHALL exit with a non-zero status when thresholds for added, removed,
or changed rows are exceeded.

#### Scenario: Threshold exceeded
- **WHEN** `--max-changed-rows` is set and the changed count is higher
- **THEN** the command exits with a non-zero status

### Requirement: Schema Diff
The system SHALL compare the schemas of two datasets and report added, removed, retyped and
nullability-changed fields, plus likely renames.

#### Scenario: Retyped column
- **WHEN** `amount` is an integer in `old.csv` and a string in `new.csv`
- **AND** user runs `undatum diff --schema old.csv new.csv`
- **THEN** the report lists `amount` as a type change from integer to string

### Requirement: Schema Drift Across File Sets
The system SHALL compare every file in a set to a baseline schema and SHALL exit non-zero when
drift matches the categories given in `--fail-on`.

#### Scenario: Drift fails CI
- **WHEN** user runs `undatum schema drift deliveries/*.csv --baseline schema.json --fail-on removed`
- **AND** one file lacks a baseline column
- **THEN** that file is reported and the command exits with code 1

