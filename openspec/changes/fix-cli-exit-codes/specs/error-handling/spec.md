## ADDED Requirements

### Requirement: Non-Zero Exit on Any Failure
A command that cannot complete its task SHALL exit with a non-zero code; reporting an error only
through logging and then returning normally MUST NOT happen.

#### Scenario: Missing required sampling size
- **WHEN** user runs `undatum sample data.csv` without `--n` or `--percent`
- **THEN** the system prints "Sample size (--n or --percent) is required"
- **AND** exits with code 1

#### Scenario: Error logged by a command
- **WHEN** a command logs a message at ERROR level because it cannot produce its result
- **THEN** the process exit code is non-zero

### Requirement: Interrupt Exit Code
The CLI SHALL exit with code 130 when the user interrupts it with Ctrl-C.

#### Scenario: User presses Ctrl-C
- **WHEN** a long-running command receives SIGINT
- **THEN** the system prints "Interrupted" to stderr without a traceback
- **AND** exits with code 130

### Requirement: Engine Option Validation
Every command with an `--engine` option SHALL accept only `auto`, `duckdb` and `python`
(with `iterable` as an alias of `python`) and SHALL reject any other value.

#### Scenario: Misspelled engine
- **WHEN** user runs `undatum sort data.csv --by a --engine duckbd`
- **THEN** the system exits with code 2 (invalid command-line usage)
- **AND** the message lists the accepted values `auto`, `duckdb`, `python`

#### Scenario: Legacy engine name
- **WHEN** user runs `undatum stats data.csv --engine iterable`
- **THEN** the command runs with the Python engine
