## ADDED Requirements

### Requirement: pandas Is an Optional Extra
The base package SHALL NOT depend on pandas. Commands and SDK methods that build DataFrames
(`extract`, `analyze --use-pandas`, `Dataset.to_pandas()`) SHALL import pandas when they run and,
when it is missing, exit with code 2 (or raise `DependencyError`) naming the extra to install.
Records undatum reads itself SHALL be described through Arrow tables, not DataFrames.

#### Scenario: Analyze XML without pandas
- **WHEN** a user installs `undatum` without extras and runs `undatum analyze books.xml`
- **THEN** the report lists the fields and their types
- **AND** pandas is not installed or imported

#### Scenario: Command that needs pandas
- **WHEN** a user without pandas runs `undatum analyze data.json --use-pandas`
- **THEN** the command exits with code 2 and explains how to install `undatum[pandas]`

#### Scenario: Extras that include pandas
- **WHEN** a user installs `undatum[extract]` or `undatum[all]`
- **THEN** pandas is installed
