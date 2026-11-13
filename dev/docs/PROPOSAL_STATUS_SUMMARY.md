# Proposal Status Summary

**Last updated:** 2026-11-13

> This file is a point-in-time snapshot. For live status, run `openspec list`.

## Archived (complete)

Many previously active changes were archived on 2026-08-12 after implementation
and/or verification, including P0/P1 user-needs work, Data API hardening, S3,
plugins, doc metadata, stats JSON, schema Excel/XML/DOCX, SDK result objects,
distribution binaries, community process docs, plot filtering/aggregation,
dictquery removal (DuckDB WHERE on frequency/uniq), stats DuckDB/progress tests,
and database ingestion leftovers (Docker/benchmarks deferred).

On 2026-08-13:

- `add-tui-interface` — `undatum tui` (extra `tui`, Textual); specs in `openspec/specs/tui/`
- `add-web-ui` — `undatum web` (extra `web`, FastAPI + Jinja2 + HTMX); specs in `openspec/specs/web-ui/`
- `remove-mistql-support` — removed `undatum query` and the `mistql` dependency; `--filter` is comparison/boolean only

On 2026-08-15:

- `add-cloud-connectors` — GCS (`gs://`/`gcs://`) and Azure (`az://`/`abfs://`)
  as first-class cloud paths (CLI, SDK, Data API, TUI/web); extras `gcs`/`azure`

On 2026-11-13, the 30 changes shipped in 1.8–2.0, in roadmap phase order:

- Phase 0 fixes: `fix-transform-output-writing`, `fix-cli-exit-codes`,
  `fix-runtime-defects`, `update-python-support-policy`
- Phase 1: `update-cli-option-conventions`, `add-stdin-stdout-pipelines`,
  `update-cli-startup-and-logging`, `update-security-hardening`
- Phase 2: `refactor-sdk-and-agent-adapters`, `remove-legacy-ai-stack`,
  `add-performance-benchmarks`
- Phase 3: `add-data-quality-report`, `add-validation-rule-library`,
  `add-machine-readable-output`, `add-sql-expression-transforms`, `add-partitioned-output`,
  `add-schema-drift-detection`, `add-clickhouse-mssql-ingestion`,
  `add-mcp-resources-and-prompts`
- 2.0: `refactor-duckdb-first-execution`, `update-python-311-duckdb-2`,
  `update-duckdb-path-startup`, `update-pandas-optional`, `add-offline-duckdb-extensions`,
  `update-excel-fastexcel`, `update-validation-sql`, `add-sdk-dataframe-interop`,
  `add-cli-manifest`, `add-odcs-contracts`, `add-result-cache`

New specs from these archives: `cli-conventions`, `cli-introspection`,
`agent-integration`, `data-validation` and `release-quality`. The last two hold only the
requirements of these changes; older archived deltas for them are not restored yet
(`add-2026-10-review-roadmap` task 2.1).

## Active — remaining

- `add-2026-10-review-roadmap` — OpenSpec hygiene is done (lost specs restored, summaries moved
  here); open: approving the plan (1.1), the review report export (1.3), reconciling the
  ingestion/analysis/visualization specs (2.2) and gate evidence (3.x).
- `remove-deprecated-cli-surface` — `scheme` and the hidden command and option aliases still ship
  in 2.0; removal waits for 3.0, with its changelog entry; `--autodoc` is undecided.
- `add-native-arrow-repack`, `add-repack-effort-trials` — not approved, not started.
- `add-distribution-channels` — the Homebrew tap is live; 1.1 closes when a release job has
  bumped it; conda-forge waits for iterabledata and qddate feedstocks.
- `refactor-streaming-operations-core` 4.2 (upstream writers and stdin to iterabledata) and
  `update-project-documentation` 4.4 (issues for `dev/docs/*`).

Done on 2026-11-13: branch protection on `master` with required checks, "Allow auto-merge", the
maintainer approval for the `pypi` environment, the stale `snyk-fix-*`/`codex/*` branches deleted
and the decision to yank 1.7.0; `fix-base-install-optional-imports`, `update-ci-enforcement`,
`update-release-pipeline` and `update-dev-tooling-and-dependencies` are archived.

Archived on 2026-11-13 as well: `add-undatum-improvement-roadmap` (4.3 streaming connectors and
4.4 synthetic data stay deferred; LLM pipeline autodoc, the visual pipeline DAG, inline plot
images and Data API embedding in the web UI remain follow-on ideas).

## Maintainer follow-up (not code)

- GitHub Discussions: https://github.com/datacoon/undatum/discussions
- structured-text-tools listing: https://github.com/dbohdan/structured-text-tools/pull/139
- CLI defaults: `defaults:` in `undatum.yaml` / `~/.undatum/config.yaml`; `undatum config show`
- Man page: `man/undatum.1` (`make man`); installed to `share/man/man1`
- `pipeline doc` emits Mermaid/Markdown diagrams; LLM pipeline autodoc remains deferred
- `pipeline run` executes live CLI commands in-process (`convert` positionals, `$step` outputs)
- Snyk bot PRs were closed; Dependabot handles security bumps
- Issue #18 (multiprocessing) closed: `--threads` ships on convert/validate/stats/frequency
