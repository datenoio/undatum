## ADDED Requirements

### Requirement: Phase-Gated Review Roadmap
The project SHALL implement the October 2026 review recommendations in four ordered phases
(0 Fix, 1 Harden, 2 Rebuild, 3 Grow) and SHALL NOT start implementing a phase until the gate
criteria of the previous phase are met and recorded.

#### Scenario: Fixes before features
- **WHEN** maintainers schedule work from the October 2026 review
- **THEN** every Phase 0 change is merged and v1.7.1 is released before any Phase 3 change is
  implemented

#### Scenario: Gate 1 criteria
- **WHEN** Phase 0 is declared complete
- **THEN** a clean wheel install starts on every supported Python version
- **AND** the command × output-format contract test matrix passes

#### Scenario: Gate 2 criteria
- **WHEN** Phase 1 is declared complete
- **THEN** lint and format checks report zero findings, the type-check ratchet is enforced in CI,
  and `undatum --help` starts in at most 0.3 seconds on the reference CI runner

#### Scenario: Gate 3 criteria
- **WHEN** Phase 2 is declared complete
- **THEN** every row-wise transform command processes 1 million CSV rows with at most 300 MB
  peak resident memory

### Requirement: Spec Tree Reflects Archived Changes
Archiving a change SHALL merge its capability deltas into `openspec/specs/` unless the change is
explicitly tooling-only and archived with `--skip-specs`.

#### Scenario: Archived capability is listed
- **WHEN** a change with deltas for capability `X` is archived without `--skip-specs`
- **THEN** `openspec list --specs` includes capability `X` with the archived requirements

#### Scenario: Periodic reconciliation
- **WHEN** a roadmap review runs
- **THEN** capabilities present only in `openspec/changes/archive/*/specs/` are reported and
  restored or explicitly retired
