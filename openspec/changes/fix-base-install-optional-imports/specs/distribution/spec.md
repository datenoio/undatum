## ADDED Requirements

### Requirement: Base Install Starts Without Optional Extras
Installing `undatum` without extras SHALL produce a working CLI: `undatum --version`,
`undatum --help` and every command that does not need an extra MUST start without import errors.

#### Scenario: Clean base install
- **WHEN** a user runs `pip install undatum` in an empty virtual environment
- **AND** runs `undatum --version`
- **THEN** the version is printed and the exit code is 0

#### Scenario: Command needing a missing extra
- **WHEN** a user without the `api` extra runs `undatum api serve config.yml`
- **THEN** the CLI prints "Missing dependency" with `pip install "undatum[api]"`
- **AND** exits with code 2

### Requirement: Lazy Loading of Optional Subsystems
Modules that depend on packages from optional extras SHALL import those packages only when a
command that needs them runs.

#### Scenario: Core import without extras
- **WHEN** `import undatum.core` runs in an environment without `fastapi`, `starlette`,
  `textual`, `jinja2`, `matplotlib` or `mcp`
- **THEN** the import succeeds
