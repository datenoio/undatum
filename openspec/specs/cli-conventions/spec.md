# cli-conventions Specification

## Purpose
Shared CLI behaviour across commands: canonical option names and short flags, deprecated aliases, standard input and output, startup time, logging, JSON results and the lean DuckDB path.
## Requirements
### Requirement: Canonical Option Vocabulary
Commands SHALL use one canonical name per concept: `--format-in`, `--format-out`, `--output`,
`--limit`, `--fields`, `--delimiter` and `--engine`; option declarations MUST come from shared
definitions rather than per-command copies.

#### Scenario: Same concept, same name
- **WHEN** a user runs `--help` on `sort`, `uniq` and `convert`
- **THEN** each shows the input format option as `--format-in`

#### Scenario: Guardrail test
- **WHEN** a new command declares a visible option named `--outtype`
- **THEN** the CLI conventions test fails

### Requirement: Deprecated Option Aliases
Replaced option names SHALL keep working as hidden aliases that print a single deprecation
warning naming the canonical option and the removal version.

#### Scenario: Old option still works
- **WHEN** user runs `undatum sort data.csv --by a --filetype csv`
- **THEN** the command succeeds
- **AND** stderr contains "Option --filetype is deprecated; use --format-in"

### Requirement: Short Flags for Common Options
Commands that accept the canonical output, limit, fields, delimiter, engine or format options
SHALL also accept the short forms `-o`, `-n`, `-f`, `-d`, `-e`, `-F` and `-O`, unique within each
command.

#### Scenario: Short output flag
- **WHEN** user runs `undatum head data.csv -n 5 -o top.jsonl`
- **THEN** five rows are written to `top.jsonl`

### Requirement: Canonical Command Names
Each capability SHALL have one canonical command shown in help; duplicates SHALL be hidden
aliases that print a deprecation warning.

#### Scenario: Hidden duplicate
- **WHEN** user runs `undatum --help`
- **THEN** `stats`, `doc` and `db load` are listed and `profile`, `document` and `ingest` are not
- **AND** `undatum profile data.csv` still runs and warns that `stats` is the canonical name

### Requirement: Standard Input Sources
Row-input commands SHALL read from standard input when the input path is `-`, detecting the
format from `--format-in` or from the leading bytes of the stream.

#### Scenario: Pipe CSV into head
- **WHEN** user runs `cat data.csv | undatum head - -n 3`
- **THEN** the first three rows of `data.csv` are printed
- **AND** the exit code is 0

#### Scenario: Chain two commands
- **WHEN** user runs `undatum sort data.csv --by a | undatum dedup -`
- **THEN** the second command reads the sorted rows from stdin

### Requirement: Standard Output Format Follows Input
When writing records to standard output, commands SHALL use the input's text format (CSV, TSV,
JSON Lines, JSON) unless `--format-out` is given.

#### Scenario: CSV in, CSV out
- **WHEN** user runs `undatum head data.csv -n 2`
- **THEN** stdout contains a CSV header and two CSV rows

#### Scenario: Explicit output format
- **WHEN** user runs `undatum head data.csv -n 2 --format-out jsonl`
- **THEN** stdout contains two JSON Lines records

### Requirement: Binary Formats on Standard Output
Commands SHALL write binary formats (Parquet, XLSX, ORC, Avro) to standard output only when
`--format-out` names the format explicitly and stdout is not a terminal.

#### Scenario: Binary output to terminal refused
- **WHEN** user runs `undatum head data.csv --format-out parquet` in an interactive terminal
- **THEN** the command exits with code 1 and suggests `--output` or a redirect

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

### Requirement: Lean DuckDB Path
A command that DuckDB runs (natively for CSV, TSV, JSON, JSON Lines and Parquet input) SHALL
NOT import iterabledata, pyarrow, pandas, openpyxl or polars, unless an option asks for a reader
or writer only they provide. Format detection SHALL recognise common file extensions without
iterabledata.

#### Scenario: Frequency on a small CSV
- **WHEN** a user runs `undatum frequency -f name data.csv` on a small file
- **THEN** the command finishes in about the time of `undatum count data.csv`
- **AND** iterabledata, pyarrow and pandas are not imported

#### Scenario: Statistics on a CSV
- **WHEN** a user runs `undatum stats data.csv`
- **THEN** the type sample is read by DuckDB with the values the Python reader gives
- **AND** pandas and iterabledata are not imported

#### Scenario: Python engine
- **WHEN** a command reads its input with the Python engine (`--engine python`, or a format
  DuckDB does not read)
- **THEN** iterabledata is imported when the input is opened

