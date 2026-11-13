# Change: Undatum Improvement Roadmap (Phased)

## Why
Undatum needs a clear, phased plan to evolve from a set of useful CLI commands into a
scalable data platform that handles large datasets, reusable workflows, data quality,
and extensibility while keeping usability high.

## Implementation Reference
**Primary Reference Document:** `dev/docs/mirothinker/MIROTHINKER_IMPROVEMENT_ROADMAP.md`

This roadmap document contains the detailed, actionable feature improvement plan with
specific goals, actions, and outcomes for each improvement area. All implementation
work should reference this document for:
- Detailed feature specifications and requirements
- Command syntax and API design examples
- Technical implementation guidance
- Success criteria and expected outcomes

The roadmap is organized into 10 major improvement areas:
1. Performance & Big Data Handling (DuckDB pushdown, parallel processing)
2. Pipelines (YAML/JSON workflows, reusable tasks)
3. Data Quality & Validation (rich validation rules, profiling)
4. Data Security (masking, anonymization, synthetic data)
5. Cloud & Database Integration (S3/GCS/Azure, database connectors)
6. Developer Experience (Python SDK, plugin system)
7. Usability & UX (CLI ergonomics, TUI/GUI)
8. Data Exploration & Visualization (plot command)
9. Documentation & Smart Help (command recipes, autodoc)
10. Phased Roadmap (Phase 1/2/3 priorities)

## What Changes
- Define a phased roadmap with concrete deliverables and scope boundaries.
- Phase 1: performance and scale foundations (DuckDB pushdown, engine selector,
  chunked/parallel processing, progress reporting), plus S3 I/O, a minimal `mask`
  command, and a basic Python SDK.
- Phase 2: workflow and quality features (pipeline run/validate, profiling in stats,
  database query/load, plot command, and command recipes/examples).
- Phase 3: ecosystem and UX expansion (plugin system, more cloud/streaming connectors,
  TUI/web UI, synthetic data, and advanced data quality monitoring).
- Establish follow-on change proposals and specs for each phase item, following the
  detailed specifications in the roadmap document.

## Impact
- Affected specs: new or updated capabilities expected for data-processing, pipeline,
  data-quality, data-security, cloud-connectors, database-ingestion, visualization,
  sdk, plugins, and cli-ux.
- Affected code: `undatum/cmds/`, `undatum/core.py`, `undatum/formats/`,
  `undatum/validate/`, `undatum/ai/`, and new modules for pipelines, SDK, plugins,
  and connectors.
