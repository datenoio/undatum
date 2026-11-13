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

### Requirement: CI Runs on the Default Branch
The main CI workflow SHALL run on every push to the default branch and on every pull request
that targets it.

#### Scenario: Push to master
- **WHEN** a commit is pushed to `master`
- **THEN** lint, tests on every supported Python version, install-gate and docs jobs run

#### Scenario: Dependency bot pull request
- **WHEN** Dependabot opens a pull request against `master`
- **THEN** the same CI jobs run on it

### Requirement: Required Merge Checks
Merging into the default branch SHALL require passing lint, test, base-install, install-gate and
docs checks.

#### Scenario: Failing check blocks merge
- **WHEN** a pull request fails the base-install job
- **THEN** it cannot be merged into `master`

### Requirement: Coverage Ratchet
CI SHALL fail when total line coverage drops below the current threshold, and the threshold SHALL
only be raised over time; pull requests SHALL meet a diff-coverage target of at least 80%.

#### Scenario: Coverage regression
- **WHEN** a pull request lowers total coverage below the configured threshold
- **THEN** the test job fails

### Requirement: Command Output Contract Tests
CI SHALL run a parametrized test suite that executes each record-writing command through the CLI
for each core output format and verifies exit code and round-tripped row count.

#### Scenario: Empty output detected
- **WHEN** a command writes a 0-byte file for a supported output format
- **THEN** the contract suite fails

### Requirement: Database Integration Tests
CI SHALL exercise database load and query commands against real PostgreSQL, MySQL, MongoDB and
Elasticsearch instances.

#### Scenario: PostgreSQL load round trip
- **WHEN** the integration job loads a fixture into PostgreSQL and queries it back
- **THEN** row count and values match the fixture

### Requirement: Minimum Dependency Verification
CI SHALL install the lowest versions allowed by `pyproject.toml` for direct dependencies and run
the test suite against them.

#### Scenario: Too-low lower bound
- **WHEN** code uses an API newer than a declared lower bound
- **THEN** the lowest-direct job fails

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

### Requirement: Pinned Single Toolchain
Formatting and linting SHALL use one formatter and one linter whose versions are pinned in a
single place and used identically by local hooks and CI.

#### Scenario: No formatter drift
- **WHEN** a contributor runs the pre-commit hooks and CI runs the format check on the same commit
- **THEN** both report the same result

### Requirement: Type-Check Ratchet
CI SHALL run the type checker for the minimum supported Python version and SHALL fail when the
number of type errors in ratcheted modules increases.

#### Scenario: New type error in a ratcheted module
- **WHEN** a pull request adds a type error in `undatum/common/`
- **THEN** the type-check job fails

### Requirement: No Legacy Build Configuration
The repository SHALL keep build, test and lint configuration only in `pyproject.toml` and the
pre-commit configuration.

#### Scenario: Stale configuration removed
- **WHEN** the repository root is listed
- **THEN** `tox.ini`, `setup.cfg`, `flake8` and `requirements.txt` are absent

