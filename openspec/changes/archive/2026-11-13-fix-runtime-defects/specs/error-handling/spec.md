## ADDED Requirements

### Requirement: Malformed Input Handling
Commands SHALL report malformed inputs (for example a database URI without credentials or a
slice without a range) as `ValidationError` with an actionable message and MUST NOT fail with
`UnboundLocalError` or `NameError`.

#### Scenario: Database URI without credentials
- **WHEN** user runs `undatum db load data.csv --db postgresql://localhost/db --table t`
- **THEN** the command either connects using defaults or exits with code 1 and a message about the
  URI, never with an internal error

#### Scenario: Slice without range
- **WHEN** user runs `undatum slice data.csv` without `--start`, `--end` or `--indices`
- **THEN** the command exits with code 1 and explains which option is required
