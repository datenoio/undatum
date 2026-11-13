## ADDED Requirements

### Requirement: Lean Base Install
The base package SHALL depend only on libraries needed by core file commands; database and search
engine drivers SHALL be optional extras, and an `all` extra SHALL install every optional feature.
`pymongo` is the exception: it provides the `bson` module that the core BSON format needs.

#### Scenario: Search engine driver is optional
- **WHEN** a user installs `undatum` without extras
- **THEN** `elasticsearch` is not installed
- **AND** `undatum db load data.csv --db elasticsearch://localhost:9200 --table t` exits with code 2 and explains how to install `undatum[elastic]`

#### Scenario: Missing database driver
- **WHEN** a user queries `clickhouse://...` without the ClickHouse driver installed
- **THEN** the command exits with code 2 and names the package to install

### Requirement: Bounded Dependency Versions
Every direct dependency SHALL declare a lower bound that CI tests and an upper bound below the
next major version unless the dependency guarantees compatibility.

#### Scenario: Unbounded dependency rejected
- **WHEN** a pull request adds a dependency without version bounds
- **THEN** a metadata check in CI fails
