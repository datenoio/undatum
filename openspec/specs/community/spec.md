# community Specification

## Purpose
Discovery listings, GitHub Discussions, and contributor-facing positioning so undatum is findable and supportable.
## Requirements
### Requirement: Discovery Listing After Trust Fixes
The project SHALL pursue listing on dbohdan/structured-text-tools only after P0 trust fixes for
gzip DuckDB routing, default Parquet usability, and streaming/low-memory Parquet conversion are
complete.

#### Scenario: List submission gating
- **WHEN** maintainers prepare a structured-text-tools submission
- **THEN** P0 items fixing gzip codec routing, Parquet default install UX, and #34-class OOM
  paths are already landed or explicitly waived with rationale

#### Scenario: Listing submitted
- **WHEN** P0 trust fixes are complete
- **THEN** a Multiformat listing pull request exists against dbohdan/structured-text-tools

### Requirement: Open Community Surface
The project SHALL maintain an open community surface including Discussions (or equivalent),
contributor documentation, and timely responses on top external issues.

#### Scenario: Contributor onboarding exists
- **WHEN** an external contributor wants to help
- **THEN** CONTRIBUTING guidance and labeled starter issues are available

#### Scenario: Top external issues get a response
- **WHEN** long-standing external issues such as large-file OOM or Homebrew install remain open
- **THEN** the issue thread includes a current status, workaround, or fix timeline

### Requirement: Release and Dependency Hygiene Signals
The project SHALL keep dependency-bot PR queues from appearing abandoned and SHALL document
CLI stability expectations for programmatic/agent users.

#### Scenario: Security bot PRs are triaged
- **WHEN** patch-level dependency bot PRs accumulate
- **THEN** they are auto-merged under policy or closed with rationale rather than left
  indefinitely unattended

#### Scenario: Stable command surface for agents
- **WHEN** a new minor/major release changes CLI command behavior
- **THEN** release notes call out breaking changes and deprecations explicitly

### Requirement: Repository Governance Files
The repository SHALL provide a security policy, issue and pull request templates and code owners,
and SHALL not keep stale automation branches.

#### Scenario: Reporting a vulnerability
- **WHEN** a researcher looks for how to report a vulnerability
- **THEN** `SECURITY.md` describes the private reporting channel and supported versions

#### Scenario: Stale bot branches
- **WHEN** an automation branch is merged or abandoned for more than 30 days
- **THEN** it is deleted from the remote

