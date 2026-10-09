## ADDED Requirements

### Requirement: Generated CLI Reference
Command reference pages SHALL be generated from the CLI command tree, and CI SHALL fail when the
committed pages differ from the generated output.

#### Scenario: New option documented automatically
- **WHEN** a pull request adds an option to `undatum sort`
- **THEN** the regenerated `sort` page lists the option with its type and default
- **AND** CI fails if the regenerated page is not committed

### Requirement: Executable Documentation Examples
Shell examples in the documentation SHALL run successfully in CI against fixture data unless they
are explicitly marked as non-runnable.

#### Scenario: Broken example detected
- **WHEN** a documented example uses an option that no longer exists
- **THEN** the docs example job fails

### Requirement: Per-Command Capability Summary
Each command page SHALL state which input formats and output formats the command supports,
whether it streams with bounded memory, and which engines it can use.

#### Scenario: Reader checks streaming support
- **WHEN** a user opens the `reverse` command page
- **THEN** the page states whether the command holds the whole dataset in memory

### Requirement: Single Developer Documentation Source
Contributor documentation (architecture, testing, release process) SHALL live in one place on
the documentation site, and other files SHALL link to it instead of duplicating it.

#### Scenario: Architecture change
- **WHEN** a module is added under `undatum/`
- **THEN** only the development section of the site needs an update

### Requirement: Review Findings Tracked as Issues
Actionable findings from review reports SHALL be filed as GitHub issues or OpenSpec changes, and
the report SHALL link to them.

#### Scenario: New review report
- **WHEN** a review report is added under `dev/docs/`
- **THEN** each actionable finding links to an issue or change id
