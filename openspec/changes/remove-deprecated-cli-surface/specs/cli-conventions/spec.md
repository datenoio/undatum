## ADDED Requirements

### Requirement: Deprecation Removal at Major Versions
Deprecated commands and option aliases SHALL remain available with warnings for at least two
minor releases and SHALL be removed only in the next major release, with a published migration
guide.

#### Scenario: Removed alias in v2.0
- **WHEN** user runs `undatum sort data.csv --by a --filetype csv` with v2.0
- **THEN** the command fails with "No such option: --filetype" and points to the migration guide

#### Scenario: Script migration helper
- **WHEN** user runs `undatum migrate-script build.sh`
- **THEN** deprecated command and option names in `build.sh` are rewritten to canonical names
