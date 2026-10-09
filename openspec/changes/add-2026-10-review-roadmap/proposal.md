# Change: Adopt the October 2026 Repository Review Roadmap

## Why
The 2026-10-07 repository review ("undatum: углублённый анализ и план улучшений",
https://claude.ai/code/artifact/11069485-001a-4ce5-9efe-4a7a6da2ade1) found that the published
1.7.0 wheel fails on a clean install, 13 transform commands silently write empty files, the main
CI workflow has never run on `master`, and none of the 2026-09-18 review findings
(`dev/docs/PRODUCT_QUALITY_REVIEW_2026-09-18.md`) were addressed. The recommendations must be
tracked as concrete, gated OpenSpec changes so that correctness lands before new features.

## What Changes
- Adopt a four-phase roadmap with explicit gates between phases:
  - Phase 0 "Fix" → v1.7.1
  - Phase 1 "Harden" → v1.8
  - Phase 2 "Rebuild" → v1.9
  - Phase 3 "Grow" → v2.0
- Map every review recommendation to exactly one change proposal (table below).
- OpenSpec hygiene: restore six capability specs that were archived but never merged into
  `openspec/specs/` (`release-quality`, `data-validation`, `documentation`, `data-analysis`,
  `database-ingestion`, `data-visualization`), archive the completed
  `add-undatum-improvement-roadmap` change, and remove stale summary files from
  `openspec/changes/`.

### Recommendation → change mapping

| Phase | Change | Review finding |
| --- | --- | --- |
| 0 | `fix-base-install-optional-imports` | Defect #0: `starlette` import breaks clean install |
| 0 | `fix-transform-output-writing` | Defect #1: empty Parquet/XLSX/TSV output, exit 0 |
| 0 | `fix-cli-exit-codes` | Defects #3, #7: errors exit 0, unchecked `--engine` |
| 0 | `fix-runtime-defects` | Defects #4, #5, #6, #9: unbound vars, API closure, ES client, SDK temp files |
| 0 | `update-ci-enforcement` | CI never runs on `master`; no contract tests |
| 0 | `update-python-support-policy` | Defect #2: Python 3.9 import failure |
| 0 | `update-release-pipeline` | Publish without tests; missing binaries; duplicated version |
| 1 | `update-cli-option-conventions` | 200 option names, 4 names for output format |
| 1 | `add-stdin-stdout-pipelines` | No stdin; stdout format ignores input |
| 1 | `update-cli-startup-and-logging` | 0.8 s startup, INFO noise on stderr |
| 1 | `update-security-hardening` | MCP SQL sandbox, `eval`, `shell=True`, TLS, API key |
| 1 | `update-dev-tooling-and-dependencies` | 4 linters, legacy configs, heavy base install |
| 1 | `update-project-documentation` | Doc drift, 7 sources of truth |
| 2 | `refactor-streaming-operations-core` | ~15 commands buffer whole dataset; monkeypatch |
| 2 | `refactor-sdk-and-agent-adapters` | SDK temp-file chaining; MCP covers 17 of 80 commands |
| 2 | `remove-legacy-ai-stack` | Duplicate AI stack, 1369 lines at 6% coverage |
| 2 | `add-performance-benchmarks` | No time/memory regression guard |
| 3 | `add-data-quality-report` | Quality report (supersedes `add-advanced-quality-monitoring`) |
| 3 | `add-validation-rule-library` | Only 5 built-in validation rules |
| 3 | `add-machine-readable-output` | `--json` on 4 commands only |
| 3 | `add-sql-expression-transforms` | No `--where` / computed columns |
| 3 | `add-partitioned-output` | No partitioned writes |
| 3 | `add-schema-drift-detection` | No schema diff |
| 3 | `add-clickhouse-mssql-ingestion` | Read-only ClickHouse/MSSQL |
| 3 | `add-mcp-resources-and-prompts` | MCP exposes tools only |
| 3 | `add-distribution-channels` | No Homebrew/Docker/conda-forge |
| 3 | `remove-deprecated-cli-surface` | Remove aliases deprecated in Phase 1 (v2.0) |

## Impact
- Affected specs: `roadmap-planning`
- Affected code: none directly; `openspec/specs/` (restored capabilities), `openspec/changes/`
- Supersedes: deferred task 4.7 of `add-undatum-improvement-roadmap`
