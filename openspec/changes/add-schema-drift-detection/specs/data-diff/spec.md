## ADDED Requirements

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
