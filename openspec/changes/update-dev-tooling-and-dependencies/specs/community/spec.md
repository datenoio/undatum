## ADDED Requirements

### Requirement: Repository Governance Files
The repository SHALL provide a security policy, issue and pull request templates and code owners,
and SHALL not keep stale automation branches.

#### Scenario: Reporting a vulnerability
- **WHEN** a researcher looks for how to report a vulnerability
- **THEN** `SECURITY.md` describes the private reporting channel and supported versions

#### Scenario: Stale bot branches
- **WHEN** an automation branch is merged or abandoned for more than 30 days
- **THEN** it is deleted from the remote
