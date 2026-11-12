## ADDED Requirements

### Requirement: Built-In Rule Library
The validator SHALL provide documented built-in rules for dates, phone numbers, ISO country,
currency and language codes, IBAN, UUID, regex patterns, uniqueness, non-null, numeric ranges and
lengths, and SHALL list them with `undatum validate --list-rules`.

#### Scenario: Country code rule
- **WHEN** a rule file declares `field: country, format: country` and a record has `country: XX`
- **THEN** the record is reported as a violation of the `country` rule

#### Scenario: Rule catalogue
- **WHEN** user runs `undatum validate --list-rules`
- **THEN** every built-in rule is listed with its parameters

### Requirement: Unknown Rule Names Are Errors
A rule file that references an unknown rule or format name SHALL fail validation setup with a
configuration error instead of skipping the check.

#### Scenario: Misspelled format
- **WHEN** a rule file declares `format: emial`
- **THEN** the command exits with code 2 and suggests `email`

### Requirement: Cross-File Reference Rules
The validator SHALL support rules that require field values to exist in a field of another file.

#### Scenario: Unknown reference value
- **WHEN** a rule declares `references: {file: countries.csv, field: code}` for field `country`
- **AND** a record has a `country` value missing from `countries.csv`
- **THEN** the record is reported as a reference violation

### Requirement: Machine-Readable Validation Results
The `validate` command SHALL output violations and summary counts as JSON or JSON Lines with a
documented, stable schema when `--format-out json` or `--format-out jsonl` is given.

#### Scenario: JSON Lines violations
- **WHEN** user runs `undatum validate data.csv --rules rules.yml --format-out jsonl`
- **THEN** each output line is one violation with `rule`, `field`, `severity`, `row` and `message`
