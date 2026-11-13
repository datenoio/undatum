## ADDED Requirements

### Requirement: Gated Publication Order
The release workflow SHALL publish to PyPI only after tests, the clean-install gate, the
distribution build and all binary builds for the same tag have succeeded.

#### Scenario: Binary build fails
- **WHEN** a binary build fails for a release tag
- **THEN** nothing is published to PyPI for that tag

#### Scenario: Clean install fails
- **WHEN** the built wheel cannot run `undatum --version` in a clean environment
- **THEN** the release stops before publication

### Requirement: Release Candidates
Release candidate tags SHALL be published to TestPyPI and verified by installing from TestPyPI
before the final release tag is created.

#### Scenario: RC verification
- **WHEN** maintainers push tag `v1.8.0rc1`
- **THEN** the package is uploaded to TestPyPI and a job installs it from TestPyPI and runs smoke
  commands

### Requirement: Single-Source Version
The package version SHALL be defined in exactly one place, and `undatum --version`, package
metadata and the release tag MUST agree.

#### Scenario: Version consistency
- **WHEN** release tag `v1.8.0` is built
- **THEN** `undatum --version` prints `undatum 1.8.0` and `pip show undatum` reports 1.8.0

### Requirement: Supply-Chain Verification
CI SHALL audit resolved dependencies for known vulnerabilities, and release artifacts SHALL carry
build provenance attestations.

#### Scenario: Vulnerable dependency
- **WHEN** a resolved dependency has a known vulnerability without a documented exception
- **THEN** the audit job fails
