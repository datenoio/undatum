## ADDED Requirements

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

#### Scenario: Extension not installed
- **WHEN** a command could use an extension that is not installed
- **THEN** it does not download the extension
- **AND** it uses the Python engine, or stops with exit code 2 naming
  `undatum extensions install <name>`

#### Scenario: Full container image
- **WHEN** a user runs the `ghcr.io/datenoio/undatum:<version>-full` image
- **THEN** `undatum extensions list` shows the four extensions as installed
