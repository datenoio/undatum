## ADDED Requirements

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
