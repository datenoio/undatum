## ADDED Requirements

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
