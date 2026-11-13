# distribution Specification

## Purpose
Installable CLI distribution: PyPI extras, pipx/uv paths, man page, shell completion, and release binaries.
## Requirements
### Requirement: First-Class Tool Install Documentation
Project documentation SHALL present `uv tool install undatum` and `pipx install undatum` as
first-class installation methods in the README install section.

#### Scenario: README lists modern tool installs
- **WHEN** a new user opens the README install section
- **THEN** `uv tool install` and `pipx install` instructions are visible near the top with
  pip/other methods

### Requirement: Official macOS Install Path
The project SHALL provide an official macOS installation path that either ships a Homebrew
formula or documents an honest supported alternative and closes the long-standing Homebrew
request accordingly.

#### Scenario: macOS user finds supported install
- **WHEN** a macOS user follows project docs to install undatum
- **THEN** they have a documented supported path (Homebrew formula and/or pipx/uv) without
  relying on an abandoned help-wanted issue alone

### Requirement: Single-Binary Release Artifacts
Release publishing SHALL include single-binary (or equivalent self-contained) artifacts for
major platforms so ops users can install without a pre-existing Python environment where
feasible.

#### Scenario: Release includes platform binaries
- **WHEN** a new undatum version is released
- **THEN** linux/mac/win self-contained artifacts are published alongside the Python package
  (or the release notes document a tracked exception)

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

### Requirement: Supported DuckDB Release Line
The package SHALL depend on a DuckDB release line that its upstream still supports (the current
line or an LTS line), and MUST move to a supported line no later than the first minor release
after its line reaches end of life.

#### Scenario: DuckDB line in support
- **WHEN** a release is built
- **THEN** the `duckdb` requirement in `pyproject.toml` admits only release lines that DuckDB
  supports on the release date
- **AND** the engine contract tests pass on the lowest admitted DuckDB version

#### Scenario: DuckDB line reaches end of life
- **WHEN** the admitted DuckDB line reaches end of life
- **THEN** the next minor release raises the `duckdb` floor to a supported line
- **AND** the CHANGELOG lists the new floor

### Requirement: Offline DuckDB Extensions
undatum SHALL provide `undatum extensions install` to download the DuckDB extensions it uses
(`encodings`, `excel`, `httpfs`, `spatial`) into a chosen directory, and `undatum extensions list`
to show which are installed. Commands SHALL use an extension only when it is already installed
in the extension directory (`UNDATUM_DUCKDB_EXTENSION_DIR` or DuckDB's default) and SHALL NOT
download extensions while they run. The `-full` container image SHALL include the extensions.

#### Scenario: Preparing an offline machine
- **WHEN** a user runs `undatum extensions install --dir /opt/ext` on a connected machine, copies
  `/opt/ext` to an offline machine and sets `UNDATUM_DUCKDB_EXTENSION_DIR=/opt/ext`
- **THEN** `undatum extensions list` on the offline machine shows the four extensions as installed

#### Scenario: Extension preinstalled
- **WHEN** `UNDATUM_DUCKDB_EXTENSION_DIR` points to a directory that contains the extension
- **AND** the machine has no network access
- **THEN** the command loads the extension from that directory and succeeds

#### Scenario: Extension missing offline
- **WHEN** a command could use an extension that is not installed
- **THEN** it does not download the extension
- **AND** it uses the Python engine, or stops with exit code 2 naming
  `undatum extensions install <name>`

#### Scenario: Release artifacts
- **WHEN** a user runs the `ghcr.io/datenoio/undatum:<version>-full` image
- **THEN** `undatum extensions list` shows the four extensions as installed

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

