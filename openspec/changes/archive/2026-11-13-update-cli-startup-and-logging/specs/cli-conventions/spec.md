## ADDED Requirements

### Requirement: Startup Time Budget
`undatum --help` and `undatum --version` SHALL complete within 0.3 seconds (median of five runs,
interpreter start included) on the reference CI runner, and importing `undatum.core` MUST NOT
import pandas, duckdb, pyarrow, matplotlib or fastapi.

#### Scenario: Version check is fast
- **WHEN** CI measures `undatum --version` five times
- **THEN** the median wall time is at most 0.3 seconds

#### Scenario: Heavy libraries stay unloaded
- **WHEN** `python -X importtime -c "import undatum.core"` runs
- **THEN** the import log contains no `pandas`, `duckdb` or `pyarrow` modules

### Requirement: Quiet Default Logging
Successful commands SHALL write nothing to stderr at the default verbosity; diagnostic messages
SHALL use loggers under the `undatum` namespace.

#### Scenario: Silent success
- **WHEN** user runs `undatum count data.csv`
- **THEN** stdout contains the count and stderr is empty

### Requirement: Global Verbosity Flags
The CLI SHALL accept `-v` (info), `-vv` (debug) and `-q` (errors only) before any command, and
per-command `--verbose` SHALL behave like `-vv`.

#### Scenario: Debug output on request
- **WHEN** user runs `undatum -vv count data.csv`
- **THEN** stderr includes debug messages such as the detected file type and engine

### Requirement: Lazy Plugin Loading
Plugin commands registered through the `undatum.commands` entry point group SHALL be imported
only when the command runs or help is rendered, and a failing plugin MUST NOT prevent unrelated
commands from running. Legacy `undatum.plugins` plugins keep loading at startup.

#### Scenario: Broken plugin does not block core commands
- **WHEN** an installed plugin raises on import and user runs `undatum head data.csv`
- **THEN** `head` runs normally
