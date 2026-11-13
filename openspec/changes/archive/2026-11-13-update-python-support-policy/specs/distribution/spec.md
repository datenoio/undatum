## ADDED Requirements

### Requirement: Supported Python Versions Policy
The project SHALL support exactly the CPython versions that have not reached end of life, and
`requires-python`, trove classifiers and the CI test matrix MUST list the same versions.

#### Scenario: Metadata and CI agree
- **WHEN** a release is built
- **THEN** every Python version in the classifiers has a passing CI job
- **AND** `requires-python` excludes every version without a CI job

#### Scenario: End-of-life version dropped
- **WHEN** a Python version reaches end of life
- **THEN** the next minor release removes it from `requires-python`, classifiers and CI
- **AND** the CHANGELOG marks the removal as breaking
