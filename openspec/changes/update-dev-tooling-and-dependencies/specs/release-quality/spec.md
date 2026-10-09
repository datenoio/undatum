## ADDED Requirements

### Requirement: Pinned Single Toolchain
Formatting and linting SHALL use one formatter and one linter whose versions are pinned in a
single place and used identically by local hooks and CI.

#### Scenario: No formatter drift
- **WHEN** a contributor runs the pre-commit hooks and CI runs the format check on the same commit
- **THEN** both report the same result

### Requirement: Type-Check Ratchet
CI SHALL run the type checker for the minimum supported Python version and SHALL fail when the
number of type errors in ratcheted modules increases.

#### Scenario: New type error in a ratcheted module
- **WHEN** a pull request adds a type error in `undatum/common/`
- **THEN** the type-check job fails

### Requirement: No Legacy Build Configuration
The repository SHALL keep build, test and lint configuration only in `pyproject.toml` and the
pre-commit configuration.

#### Scenario: Stale configuration removed
- **WHEN** the repository root is listed
- **THEN** `tox.ini`, `setup.cfg`, `flake8` and `requirements.txt` are absent
