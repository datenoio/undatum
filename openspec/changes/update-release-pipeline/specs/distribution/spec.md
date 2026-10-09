## MODIFIED Requirements

### Requirement: Single-Binary Release Artifacts
Release publishing SHALL include single-binary (or equivalent self-contained) artifacts for
major platforms so ops users can install without a pre-existing Python environment where
feasible. Binary builds SHALL succeed before the Python package is published for the same tag.

#### Scenario: Release includes platform binaries
- **WHEN** a new undatum version is released
- **THEN** linux/mac/win self-contained artifacts are published alongside the Python package
  (or the release notes document a tracked exception)

#### Scenario: Binary packaging change is tested before release
- **WHEN** a pull request changes `packaging/` or the release workflow
- **THEN** CI builds and smoke-tests the binaries on that pull request
