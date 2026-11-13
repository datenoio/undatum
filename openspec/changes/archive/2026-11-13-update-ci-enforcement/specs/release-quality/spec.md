## ADDED Requirements

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
