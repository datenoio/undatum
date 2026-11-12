## ADDED Requirements

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
Commands that need a DuckDB extension SHALL work without network access when the extension is
installed in the configured extension directory, and SHALL fail with a configuration error that
names the extension when it is missing.

#### Scenario: Extension preinstalled
- **WHEN** `UNDATUM_DUCKDB_EXTENSION_DIR` points to a directory that contains the extension
- **AND** the machine has no network access
- **THEN** the command loads the extension from that directory and succeeds

#### Scenario: Extension missing offline
- **WHEN** a command needs an extension that is not installed and cannot be downloaded
- **THEN** the command exits with code 2
- **AND** the message names the extension and how to install it for offline use

#### Scenario: Release artifacts
- **WHEN** the Docker image or a single-file binary is built
- **THEN** it contains every DuckDB extension that undatum loads
