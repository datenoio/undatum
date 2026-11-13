# examples Specification

## Purpose
Copy-paste recipes (`undatum examples list` / `show` / `run`) for common conversion, validation, and database tasks.
## Requirements
### Requirement: Examples Command
The system SHALL provide an `examples` command group for managing and executing recipe libraries.

#### Scenario: List available recipes
- **WHEN** user runs `undatum examples list`
- **THEN** the system SHALL display all available recipes
- **AND** show recipe name, description, and category
- **AND** format output in a readable table

#### Scenario: List recipes by category
- **WHEN** user runs `undatum examples list --category conversion`
- **THEN** the system SHALL filter recipes by category
- **AND** display only recipes in the specified category

#### Scenario: Show recipe details
- **WHEN** user runs `undatum examples show csv-to-jsonl`
- **THEN** the system SHALL display full recipe details
- **AND** show description, commands, and variables
- **AND** show example usage

#### Scenario: Run recipe with variables
- **WHEN** user runs `undatum examples run csv-to-jsonl --var input=data.csv --var output=data.jsonl`
- **THEN** the system SHALL substitute variables in recipe commands
- **AND** execute the commands
- **AND** display results

#### Scenario: Run recipe in dry-run mode
- **WHEN** user runs `undatum examples run csv-to-jsonl --dry-run --var input=data.csv`
- **THEN** the system SHALL show commands that would be executed
- **AND** show variable values
- **AND** not execute any commands

### Requirement: Recipe Format
Recipes SHALL be defined in a structured format with metadata and command templates.

#### Scenario: Recipe file structure
- **WHEN** recipe file is loaded
- **THEN** the system SHALL parse recipe metadata
- **AND** extract command templates
- **AND** extract variable definitions
- **AND** validate recipe structure

#### Scenario: Variable substitution
- **WHEN** recipe contains variable placeholders
- **THEN** the system SHALL substitute variables with provided values
- **AND** use default values if not provided
- **AND** validate required variables are provided

### Requirement: Recipe Library
The system SHALL provide a library of common recipes for typical data processing tasks.

#### Scenario: Conversion recipes
- **WHEN** user lists recipes
- **THEN** the system SHALL include conversion recipes
- **AND** recipes for CSV to JSONL, JSONL to CSV, etc.

#### Scenario: Validation recipes
- **WHEN** user lists recipes
- **THEN** the system SHALL include validation recipes
- **AND** recipes for data quality checks, schema validation, etc.

#### Scenario: Database recipes
- **WHEN** user lists recipes
- **THEN** the system SHALL include database recipes
- **AND** recipes for querying databases, loading data, etc.

### Requirement: Recipe Execution
The system SHALL execute recipes with proper variable substitution and error handling, and SHALL
run each command as an argument list without a shell so that substituted values cannot inject
commands.

#### Scenario: Execute recipe
- **WHEN** user runs a recipe
- **THEN** the system SHALL substitute variables
- **AND** execute commands in sequence
- **AND** handle errors gracefully
- **AND** display command output

#### Scenario: Interactive execution
- **WHEN** user runs recipe with `--interactive`
- **THEN** the system SHALL prompt for variable values
- **AND** show command preview
- **AND** ask for confirmation before execution

#### Scenario: Dry-run execution
- **WHEN** user runs recipe with `--dry-run`
- **THEN** the system SHALL show commands that would be executed
- **AND** show variable values
- **AND** not execute any commands

#### Scenario: Shell metacharacters in a variable
- **WHEN** a variable value is `data.csv; rm -rf ~`
- **THEN** the value is passed to the command as one literal argument and no shell runs it

