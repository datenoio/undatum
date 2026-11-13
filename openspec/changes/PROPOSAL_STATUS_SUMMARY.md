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

- `add-undatum-improvement-roadmap` — tasks 4.3 (`add-streaming-connectors`) and 4.4
  (`add-synthetic-data`) are deferred; 4.7 (`add-advanced-quality-monitoring`) is superseded
  by the archived `add-data-quality-report`. LLM pipeline autodoc stays deferred.
  Visual pipeline DAG, inline plot images, and Data API embed from the web UI
  remain follow-on (not in the archived web UI change).
- `add-2026-10-review-roadmap` — milestones, OpenSpec hygiene and gate evidence not recorded.
- `remove-deprecated-cli-surface` — `scheme` and the hidden command and option aliases are
  still shipped in 2.0; removal and its changelog entry remain.
- `add-native-arrow-repack`, `add-repack-effort-trials` — not approved, not started.
- `add-distribution-channels` — Homebrew tap needs the tap repository and secrets;
  conda-forge waits for iterabledata and qddate feedstocks.
- Repository settings, not code: branch protection on `master` (`update-ci-enforcement`),
  Dependabot auto-merge and stale `snyk-fix-*`/`codex/*` branches
  (`update-dev-tooling-and-dependencies`), protected `pypi` environment
  (`update-release-pipeline`).
- Leftovers tied to v1.7.1 in `fix-base-install-optional-imports` and
  `update-release-pipeline`; 1.8.0, 1.9.1 and 2.0.0 have shipped since.
- `refactor-streaming-operations-core` 4.2 (upstream writers and stdin to iterabledata) and
  `update-project-documentation` 4.4 (issues for `dev/docs/*`).

## Maintainer follow-up (not code)

- GitHub Discussions: https://github.com/datacoon/undatum/discussions
- structured-text-tools listing: https://github.com/dbohdan/structured-text-tools/pull/139
- CLI defaults: `defaults:` in `undatum.yaml` / `~/.undatum/config.yaml`; `undatum config show`
- Man page: `man/undatum.1` (`make man`); installed to `share/man/man1`
- `pipeline doc` emits Mermaid/Markdown diagrams; LLM pipeline autodoc remains deferred
- `pipeline run` executes live CLI commands in-process (`convert` positionals, `$step` outputs)
- Snyk bot PRs were closed; Dependabot handles security bumps
- Issue #18 (multiprocessing) closed: `--threads` ships on convert/validate/stats/frequency
