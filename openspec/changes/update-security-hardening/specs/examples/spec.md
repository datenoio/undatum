## MODIFIED Requirements

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
