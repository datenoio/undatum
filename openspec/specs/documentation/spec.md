# documentation Specification

## Purpose
User documentation that is honest about format support and gets people to a first success: the format support matrix, task-oriented quickstarts and the tool positioning page.
## Requirements
### Requirement: Honest Format Support Matrix
Documentation SHALL publish a format-support matrix that states read/write capability, required
extras, and streaming support for supported formats.

#### Scenario: User checks whether a format is writable
- **WHEN** a user consults the format-support matrix for a format that is read-only
- **THEN** the matrix clearly marks write as unsupported (or limited) rather than implying full
  bidirectional support

### Requirement: Task-Oriented Quickstarts
Documentation SHALL include short task-oriented quickstarts for common success paths.

#### Scenario: CSV to Parquet quickstart
- **WHEN** a new user follows the CSV→Parquet quickstart
- **THEN** they can complete a successful conversion using the documented commands within minutes

#### Scenario: Validate-before-publish quickstart
- **WHEN** a publisher follows the validation quickstart
- **THEN** docs show how to run `validate` (and related packaging steps where applicable) on a
  sample dataset

### Requirement: Tool Positioning Page
Documentation SHALL include a positioning page that explains when to choose undatum versus
common alternatives (miller, DuckDB, csvkit).

#### Scenario: Evaluator compares tools
- **WHEN** a reader opens the positioning page
- **THEN** it states undatum's strengths (multiformat streams, validation/masking, agent-native)
  and when alternatives may be a better fit
