## 1. Roadmap Documentation
- [x] 1.1 Create proposal.md with roadmap overview and reference to implementation document
- [x] 1.2 Add spec delta for roadmap-planning capability
- [x] 1.3 Validate proposal structure

## 2. Phase 1: Foundation Change Proposals
Create OpenSpec change proposals for immediate impact items:

- [x] 2.1 Create `improve-duckdb-operations` proposal
  - Push more operations through DuckDB (sort, frequency, uniq, sample, search, dedup, slice, join)
  - Add `--engine auto|duckdb|python` selector
  - Expose DuckDB tuning options (--duckdb-threads, --duckdb-memory, --duckdb-temp-dir)

- [x] 2.2 Create `add-parallel-processing` proposal
  - Implement chunked streaming I/O
  - Add `--threads N` for CPU-bound operations
  - Add `--progress` flag with progress bar/percentage

- [x] 2.3 Create `add-s3-connector` proposal
  - Add S3 URI support (s3://bucket/path)
  - Respect AWS credentials from environment
  - Support read/write operations for major commands

- [x] 2.4 Create `add-mask-command` proposal
  - Implement `undatum mask` command
  - Support methods: redact, hash, randomize
  - Handle PII protection use cases

- [x] 2.5 Create `add-python-sdk` proposal
  - Design Dataset API (read, transform, write)
  - Map CLI commands to SDK methods
  - Ensure consistent behavior between CLI and SDK

## 3. Phase 2: Workflow & Quality Change Proposals
Create OpenSpec change proposals for workflow and quality features:

- [x] 3.1 Create `add-pipeline-command` proposal
  - Implement `pipeline run` and `pipeline validate` subcommands
  - Define YAML/JSON pipeline spec format
  - Support variables and overrides

- [x] 3.2 Create `add-pipeline-templates` proposal
  - Implement reusable tasks (profile_dataset, generate_docs)
  - Add `pipeline templates list` and `pipeline templates init` commands
  - Ship templates for common workflows

- [x] 3.3 Create `enhance-stats-profiling` proposal
  - Extend stats with missing value rates, distinct counts, cardinality
  - Add type inference (categorical vs numerical)
  - Add distribution info (mean, median, percentiles)
  - Add `profile` alias command

- [x] 3.4 Create `add-rich-validation-rules` proposal
  - Support YAML/JSON rule definitions
  - Implement hard errors and soft warnings
  - Add violation summary reporting

- [x] 3.5 Create `add-db-query-load` proposal
  - Implement `db query` command
  - Implement `db load` command
  - Support PostgreSQL, MySQL/MariaDB, SQLite

- [x] 3.6 Create `add-plot-command` proposal
  - Implement `plot` command for visualizations
  - Support histogram, bar plot types
  - Add matplotlib backend (optional plotly/bokeh)

- [x] 3.7 Create `add-examples-command` proposal
  - Implement `examples list` and `examples run` commands
  - Create recipe library for common tasks
  - Make recipes copy-paste ready

## 4. Phase 3: Ecosystem & UX Change Proposals
Create OpenSpec change proposals for ecosystem expansion:

- [x] 4.1 Create `add-plugin-system` proposal
  - Design entry point system (undatum.plugins)
  - Define plugin API for commands, IO connectors, transforms
  - Support plugin discovery and registration

- [x] 4.2 Create `add-cloud-connectors` proposal — implemented and archived (`gs://`/`gcs://`, `az://`/`abfs://`; extras `gcs`/`azure`/`cloud`)
- [ ] 4.3 Create `add-streaming-connectors` proposal — deferred
- [ ] 4.4 Create `add-synthetic-data` proposal — deferred
- [x] 4.5 Create `add-tui-interface` proposal — implemented and archived (`undatum tui`)
- [x] 4.6 Create `add-web-ui` proposal — implemented and archived (`undatum web`); visual DAG / plotly / Data API embed remain follow-on
- [x] 4.7 Create `add-advanced-quality-monitoring` proposal — superseded by `add-data-quality-report`
- [x] 4.8 Create `add-pipeline-autodoc` proposal — `pipeline doc` ships Mermaid/Markdown diagrams; LLM autodoc remains deferred
- [x] 4.9 Create `improve-cli-ergonomics` proposal — `--version`, `--install-completion`, and `undatum(1)` man page ship; TUI/web extras are optional

## 5. Coordination & Tracking
- [x] 5.1 Track progress of Phase 1 proposals
- [x] 5.2 Coordinate dependencies between proposals
- [x] 5.3 Update roadmap document as proposals are completed
- [x] 5.4 Review and prioritize Phase 2/3 proposals based on Phase 1 learnings
  - Phase 3 child proposals remain deferred until demand is clear

