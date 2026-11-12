# data-security Specification

## Purpose
Mask or redact sensitive fields (`undatum mask`) so datasets can be shared without exposing PII.
## Requirements
### Requirement: Mask Command
The system SHALL provide a `mask` command for anonymizing sensitive data fields.

#### Scenario: Mask fields with redact method
- **WHEN** user runs `undatum mask input.csv --fields email,phone --method redact --output masked.csv`
- **THEN** email and phone fields are replaced with fixed token (e.g., `***`)

#### Scenario: Mask fields with hash method
- **WHEN** user runs `undatum mask input.jsonl --fields user_id --method hash --output masked.jsonl`
- **THEN** user_id field is replaced with deterministic hash, preserving ability to join on hashed
  values while hiding original identities

#### Scenario: Mask fields with randomize method
- **WHEN** user runs `undatum mask input.csv --fields age,email --method randomize --output masked.csv`
- **THEN** age and email fields are replaced with random but type-compatible values (e.g., random
  age in reasonable range, random email format)

### Requirement: Multiple Field Masking
The mask command SHALL support masking multiple fields in a single operation.

#### Scenario: Mask multiple fields
- **WHEN** user runs `undatum mask input.csv --fields ssn,email,phone --method hash`
- **THEN** all specified fields are masked using the same method

### Requirement: Format Support
The mask command SHALL support masking data in multiple formats (CSV, JSONL, JSON).

#### Scenario: Mask CSV data
- **WHEN** user runs `undatum mask data.csv --fields email --method redact`
- **THEN** CSV data is masked and output in CSV format

#### Scenario: Mask JSONL data
- **WHEN** user runs `undatum mask data.jsonl --fields phone --method hash`
- **THEN** JSONL data is masked and output in JSONL format

### Requirement: Agent Tool Filesystem Sandbox
Agent-facing tools (MCP server and LangChain tools) SHALL only read and write files inside a
configured sandbox root and SHALL reject any path that resolves outside it.

#### Scenario: Path traversal rejected
- **WHEN** an agent calls `read_sample` with path `../../etc/passwd` and the root is the project
  directory
- **THEN** the tool returns an error with code `path_outside_root` and reads nothing

#### Scenario: Symlink escape rejected
- **WHEN** a path inside the root is a symlink to a file outside the root
- **THEN** the tool rejects it

### Requirement: Read-Only SQL for Agent Tools
The agent `query_sql` tool SHALL execute exactly one read-only `SELECT` statement with DuckDB
external access disabled except for the sandbox root.

#### Scenario: Write attempt blocked
- **WHEN** an agent calls `query_sql` with `COPY (SELECT 1) TO '/tmp/x.csv'`
- **THEN** the tool returns an error and no file is written

#### Scenario: Reading outside the sandbox blocked
- **WHEN** an agent calls `query_sql` with `SELECT * FROM read_text('/etc/hosts')`
- **THEN** the tool returns an error

### Requirement: TLS Verification by Default
Database and search-engine connectors SHALL verify TLS certificates by default and SHALL disable
verification only through an explicit `--insecure` option that prints a warning.

#### Scenario: Self-signed certificate
- **WHEN** user loads data into an Elasticsearch cluster with a self-signed certificate without
  `--insecure` or `--ca-cert`
- **THEN** the command fails with a certificate verification error and suggests `--ca-cert`

