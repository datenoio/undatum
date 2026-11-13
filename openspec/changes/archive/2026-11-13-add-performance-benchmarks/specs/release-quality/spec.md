## ADDED Requirements

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
