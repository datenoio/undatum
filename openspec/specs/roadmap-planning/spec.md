# roadmap-planning Specification

## Purpose
User-needs roadmap that prefers install, memory, and correctness work over further niche format expansion.
## Requirements
### Requirement: User-Needs Improvement Roadmap
The project SHALL maintain a user-needs-driven improvement roadmap that prioritizes trust,
scalability, and distribution based on external issue signals before further feature expansion.

#### Scenario: Authoritative reference document
- **WHEN** planning or implementing improvements derived from user feedback
- **THEN** `dev/docs/undatum-improvement-recommendations.md` is the authoritative reference for
  prioritized recommendations, evidence, and sequencing guidance

#### Scenario: Priority sequencing
- **WHEN** scheduling roadmap work
- **THEN** P0 trust/correctness items are completed before discovery outreach and before
  further niche format expansion

#### Scenario: Mapping to concrete change proposals
- **WHEN** a numbered recommendation in the reference document is actionable engineering work
- **THEN** it is tracked as a verb-led OpenSpec change proposal (or explicitly mapped to an
  existing proposal) under `openspec/changes/`

### Requirement: Consolidate Before Expanding
The project SHALL prefer closing install, memory, and correctness gaps over adding new format
breadth until core large-file and default-install paths are reliable.

#### Scenario: Defer niche formats
- **WHEN** evaluating low-priority format requests (e.g. Veriform)
- **THEN** they are deferred or closed as not planned until P0 trust items are complete

#### Scenario: Agent features ride on hardened core
- **WHEN** prioritizing MCP/AI/agent features relative to convert/stats reliability
- **THEN** agent-facing work does not supersede fixes for install breakage and multi-GB OOM paths

### Requirement: Phased Improvement Roadmap
The project SHALL maintain a phased improvement roadmap that defines concrete deliverables,
scope boundaries, and implementation priorities for evolving undatum from a collection of
CLI commands into a scalable data platform.

#### Scenario: Roadmap reference for implementation
- **WHEN** implementing new features or capabilities
- **THEN** the roadmap document (`dev/docs/mirothinker/MIROTHINKER_IMPROVEMENT_ROADMAP.md`)
  serves as the authoritative reference for detailed specifications, goals, actions, and
  expected outcomes

#### Scenario: Phased delivery approach
- **WHEN** planning feature development
- **THEN** features are organized into three phases (Phase 1: foundations, Phase 2: workflows,
  Phase 3: ecosystem) with clear priorities and dependencies

