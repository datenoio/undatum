## ADDED Requirements

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
