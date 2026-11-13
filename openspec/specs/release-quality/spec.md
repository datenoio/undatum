# release-quality Specification

## Purpose
Release gates that keep undatum installable, tidy and fast: the clean-install wheel smoke gate, release artifact hygiene and performance regression checks in CI.
## Requirements
### Requirement: Clean-Install Wheel Smoke Gate
CI SHALL verify that a freshly installed wheel from the built distribution can import and run
core CLI smoke commands without missing declared dependencies.

#### Scenario: Wheel install on clean venv
- **WHEN** CI builds a wheel and installs it into a clean virtualenv
- **THEN** `undatum --help` (or equivalent entry point) runs successfully

#### Scenario: Core command smoke on installed wheel
- **WHEN** CI runs smoke convert/stats/validate against fixture files for core formats after
  clean wheel install
- **THEN** commands exit successfully and do not raise `ModuleNotFoundError` for packages that
  are declared dependencies

### Requirement: Release Artifact Hygiene
The repository SHALL avoid committing generated reports, IDE metadata, and oversized local data
dumps that are not required fixtures, and SHALL keep CHANGELOG version sections complete with
real dates.

#### Scenario: No generated reports in tree
- **WHEN** a contributor clones the repository
- **THEN** generated artifacts such as pylint report dumps and IDE project dirs are absent or
  gitignored

#### Scenario: CHANGELOG dates are concrete
- **WHEN** a reader opens `CHANGELOG.md` for released versions
- **THEN** version headings use concrete dates (not placeholders like `2024-XX-XX`) and released
  versions have corresponding sections

### Requirement: Performance Regression Gates
CI SHALL measure wall time and peak resident memory of core commands on reference datasets and
SHALL fail when a command exceeds its recorded budget or regresses by more than 20% against the
default branch.

#### Scenario: Memory regression caught
- **WHEN** a pull request makes `rename` hold all rows in memory
- **THEN** the benchmark job fails because peak RSS on the 100k-row dataset exceeds the budget

#### Scenario: Nightly history
- **WHEN** the nightly benchmark job finishes
- **THEN** results for the 1M-row tier are stored as an artifact and appended to the published
  history

