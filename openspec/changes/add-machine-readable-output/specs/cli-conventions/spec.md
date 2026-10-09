## ADDED Requirements

### Requirement: JSON Output for Informational Commands
Every command that reports information rather than records SHALL support `--format-out json`
(and `--json`), printing exactly one JSON document to stdout with no other text.

#### Scenario: Count as JSON
- **WHEN** user runs `undatum count data.csv --json`
- **THEN** stdout is `{"schema": "undatum.count/1", "file": "data.csv", "rows": 1000}`

#### Scenario: Error in JSON mode
- **WHEN** user runs `undatum stats missing.csv --json`
- **THEN** stderr contains a JSON error object with code `file_not_found`
- **AND** the exit code is 1

### Requirement: Stable Result Schemas
JSON results SHALL carry a schema identifier with a major version, and incompatible changes SHALL
increase that version.

#### Scenario: Schema version bump
- **WHEN** a field is removed from the stats JSON result
- **THEN** the schema id changes from `undatum.stats/1` to `undatum.stats/2` and the CHANGELOG
  says so
