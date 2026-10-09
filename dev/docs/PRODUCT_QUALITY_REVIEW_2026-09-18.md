# undatum — Product & Quality Review, Improvements Plan

**Date:** 2026-09-18 · **Scope:** v1.7.0 (master @ 57649a2) · **Method:** 4 parallel audits (feature inventory, code quality, tests/coverage, documentation)

## Executive Summary

undatum 1.7.0 is functionally strong: **46 top-level commands across 10 sub-apps, a fully green test suite (1131 passed / 0 failed / 21 skipped in 18 s), and complete user-facing command documentation** (57 pages). The product surface is broad and coherent at the user-doc level.

The debt is concentrated underneath:

1. **Release blocker:** the package claims Python 3.9 support (`requires-python = ">=3.9"`, CI has a 3.9 job) but 4 modules use `X | Y` union annotations without `from __future__ import annotations` — they **crash at import on Python 3.9**.
2. **Latent crash bugs:** 8 unbound-variable defects (sampler, slicer ×3, postgres/mysql ingesters, schema_utils), a loop-closure bug that corrupts `api serve` route limits, and an Elasticsearch client call (`timeout=`) that ES 8.x rejects at runtime.
3. **Quality gates exist but don't gate:** 18 ruff errors, 12 files failing black, 710 mypy errors in 86 of 148 files; coverage tooling isn't even installed in the dev venv, so the coverage number is unknown.
4. **UX drift across the command surface:** two engine vocabularies (`python` vs `iterable`), two input-format flags (`--filetype` vs `--format-in`), two ingestion paths (`ingest` vs `db load`), three doc-generation paths.
5. **Contributor-facing docs are stale** (WORKFLOW_GUIDE, openwiki, AGENTS.md tree) while user-facing docs are excellent.

**Recommended action:** run Phase 0 (correctness) immediately as patch-release candidates for v1.7.1; then execute Phases 1–2 (quality gates + UX coherence) before the next feature work; Phases 3–5 (test depth, new features, docs) can be scheduled as OpenSpec proposals per the roadmap-planning spec.

---

## Current State Snapshot (verified this review)

| Dimension | Status | Evidence |
|---|---|---|
| Test suite | ✅ Green — 1131/1152 passed, 0 failed, 21 skipped (optional deps), 18.1 s | `pytest -q` in `.venv` (py3.13) |
| Coverage | ❓ Unknown — pytest-cov/coverage not installed in `.venv` | prerequisite missing |
| ruff | ❌ 18 errors (3 auto-fixable): B023×4, UP045×5, E731×3, UP035×2, B007×2, F841, F401 | `ruff check undatum/` |
| black | ❌ 12/229 files drift (black 25.x vs unpinned dev extra) | `black --check` |
| mypy (py39) | ❌ 710 errors / 86 files; hotspot `cli/data_commands.py` = 225 (32%) | `mypy undatum/` |
| pylint (E) | ⚠️ ~22 real errors after filtering ext-module false positives | E0606×8, E1123×3, E0611×3, E1102×3, E0603×3 |
| Command docs | ✅ Complete — every command + alias + deprecated `scheme` mapped | `docs/docs/commands/` |
| Contributor docs | ❌ Stale — WORKFLOW_GUIDE cites archived change; openwiki lists removed `query` cmd | see Phase 5 |
| Docstrings | ❌ ~40% of functions have any docstring; 0 `Example:` sections in 10-module sample | cmds/ sample |
| OpenSpec hygiene | ⚠️ 2 stale summary files in `changes/` root; 1 completed change not archived | `openspec/changes/` |

---

## Phase 0 — Correctness & Release Blockers (target: v1.7.1 patch)

*Bug fixes restoring intended behavior — per OpenSpec rules these do not need proposals.*

| # | Item | Where | Why | Effort |
|---|---|---|---|---|
| 0.1 | **Fix Python 3.9 import crashes** — add `from __future__ import annotations` (or revert to `Optional`) in 4 modules causing 37 mypy `[syntax]` errors | `undatum/common/command_utils.py:38-42`, `undatum/cmds/converter.py:75`, `undatum/cmds/schemer.py`, `undatum/cmds/selector.py` | Package advertises py3.9 and CI runs a 3.9 job, yet these modules raise `TypeError` at import on 3.9 | S |
| 0.2 | **Fix 8 unbound-variable crash paths** (pylint E0606) | `cmds/sampler.py:97` (`query`); `cmds/slicer.py:76,148,152`; `cmds/ingester/postgres.py:112` + `cmds/ingester/mysql_backend.py:100` (`rest` undefined when URI has no `@`); `common/schema_utils.py:313` | Real crashes on reachable paths, not style | S–M |
| 0.3 | **Fix loop-closure bug in API server** — 5 route handlers capture loop vars `max_limit`/`default_limit`; bind as default args | `cmds/api.py:703-725` (ruff B023) | All generated routes silently use the last iteration's limits | S |
| 0.4 | **Fix Elasticsearch client call** — `timeout=` → `request_timeout=`, pin `elasticsearch` major, make `verify_certs` configurable (currently hardcoded `False`) | `cmds/ingester/elastic.py:28` | Live runtime failure on fresh installs with ES 8.x; TLS verification silently disabled | S |
| 0.5 | **Verify/raise `iterabledata` floor** — `open_iterable` import flagged missing from `iterable.helpers.detect` | `common/db_source.py:24`, `common/s3_iterable.py:9`, `sdk/dataset.py:8`; pin in `pyproject.toml` | E0611 suggests `>=1.0.18` floor may be too low | S |

## Phase 1 — Quality Gates That Actually Gate

| # | Item | Detail | Effort |
|---|---|---|---|
| 1.1 | **Zero the ruff error count** — 18 errors, 14 mechanical (UP045/UP035/E731/F401/F841/B007); fix B023 (0.3) + E731 lambdas (`ai/doc_enrichment.py:106,115`, `sorter.py:183`) | Add `--fix` run + manual passes; keep at zero via CI | S |
| 1.2 | **Pin dev-tool versions** — black/ruff/mypy versions in `dev` extra or pre-commit; reformat the 12 drifting files once | Kills recurring format drift | S |
| 1.3 | **Install pytest-cov; set coverage baseline + ratchet** (`--cov-fail-under`) in CI | Current coverage is unmeasurable; establish number first, ratchet up per module | S |
| 1.4 | **Mypy ratchet** — fix the 372 `[assignment]` errors (mostly implicit-Optional in `cli/data_commands.py`), enable `disallow_incomplete_defs`, per-module exclude list shrinking over time | 710 → manageable; start with `common/` + `sdk/` | L |
| 1.5 | **Bound core dependencies** — 10 unpinned core deps incl. `pydantic` (v1/v2 break), `duckdb`, `typer`, `elasticsearch`; add upper bounds; raise `iterabledata` floor | Prevents repeat of the elastic break | S |
| 1.6 | **Move `pymongo`/`elasticsearch`/`dnspython` out of core deps** into `mongo`/`elastic` extras | Consistent with postgres/mysql being extras; lighter base install | M (breaking-ish: needs CHANGELOG + docs) |
| 1.7 | **Kill deprecation noise** — `datetime.utcnow()` (own code + iterable), qddate/pyparsing pins; add a `-W error::DeprecationWarning` CI job scoped to own code | 4200 warnings currently mask real signals | M |
| 1.8 | **Security hardening** — replace `eval()` on user YAML rule conditions with an AST-whitelist evaluator (`common/validation_rules.py:215`; the field-name string-replacement at :210 is fragile — a field named `or` corrupts the expression); sanitize `_substitute_variables` shell interpolation in `cmds/examples.py:320` | User-controlled expressions reach `eval`/`shell=True` | M |

## Phase 2 — UX Coherence (command-surface unification)

| # | Item | Detail | Effort |
|---|---|---|---|
| 2.1 | **Unify engine vocabulary** — `'python'` vs `'iterable'` across convert (`cli/data_commands.py:198`), frequency (:794) vs uniq (:514), select (:894), stats (:658), analyze (:1282); convert's own docstring example uses `--engine iterable` (:337) while choices say `python` | Accept both as aliases, document one | S |
| 2.2 | **Unify `--filetype` → `--format-in`** with back-compat alias (uniq :501, frequency :781; ~20 commands use `--format-in`) | One flag name everywhere | S |
| 2.3 | **Converge ingestion UX** — `ingest` (positional `uri db table`) vs `db load` (`--db/--table`); deprecate one path with alias; also fix `ingest --timeout` default of `-30` (:1921-1923) | Two ingestion styles confuse users | M |
| 2.4 | **Converge doc-generation UX** — `doc` / `document` / `ai doc` (doc --autodoc ≈ ai doc); pick canonical, alias rest | M |
| 2.5 | **Remove dead/contradictory options** — `headers` unused `fields`/`--filter` args (:567-569, :585-588); `stats` redundant `--progress` + `--no-progress` (:651-654); `--start-page` help text contradicts itself across convert (:153) vs doc (:1490) | S |
| 2.6 | **Refresh stale spec scenarios** — cloud-connectors spec uses `convert X --output Y` but OUTPUT is positional (`openspec/specs/cloud-connectors/spec.md:12-59` vs `data_commands.py:131-132`); ingest scenario omits required positionals (:46) | Specs must describe a CLI that parses | S |
| 2.7 | **Standardize error handling** — 7 of 45 cmd modules bypass the `UndatumError` hierarchy (`differ.py`, `doc.py`, `plotter.py`, `sniffer.py`, `table.py`, `textproc.py`; e.g. bare `except Exception` + `sys.exit(1)` in plot :3581-3587); audit the 182 broad `except Exception` blocks | Violates own error-handling spec | M |
| 2.8 | **Cloud-URI parity audit + matrix doc** — `path_utils.py` handles gs/az but support is command-dependent; publish a command × cloud-scheme support matrix | Users can't predict where s3://gs://az:// works | M |

## Phase 3 — Test Depth (after 1.3 baseline exists)

| # | Item | Detail | Effort |
|---|---|---|---|
| 3.1 | **Dedicated test files for 11 smoke-only commands** — exploder, filler, fixlengths, formatter, joiner, replacer, sampler, searcher, slicer, sniffer, transposer (currently 1–3 tests each inside test_phase1/2/3) | Edge cases (empty input, bad encoding, missing keys) untested | L |
| 3.2 | **Tests for `examples` and `pipeline_templates`** — zero coverage on shipped commands | S |
| 3.3 | **Real DB integration tests** — Postgres/MySQL via Docker service in CI; 16 ingester tests currently skip and the rest are mock-only (126 mock refs in test_ingester.py) | `db load` regressions ship silently today | M |
| 3.4 | **Populate benchmarks** — tests/benchmarks/ has 2 skipped tests only; add convert/stats benchmarks guarding the streaming/low-memory claims; add pytest-benchmark to dev extra | Performance claims are untested | M |
| 3.5 | **Fixture dedup + shared edge-case fixtures** — ~10 local `sample_csv_file` redefinitions → conftest; add malformed/empty/multi-file fixtures | S |
| 3.6 | **Delete `tests/test.py`** stray debug script; fix lone `assert True` in test_iterabledata_migration.py:235 | S |
| 3.7 | **Contract-level assertions for S3/AI mock tests** — test_s3_iterable.py (85 mock refs) and test_ai_cli.py (33) assert mock calls, not payloads | M |

## Phase 4 — Feature Opportunities (route through OpenSpec proposals)

Ranked by user value from the inventory audit:

1. **ClickHouse/MSSQL write support in `db load`/`ingest`** — read support exists (`cli/db_cli.py:44-45`), write is the obvious gap (`cmds/ingester/` has 6 backends, neither of these).
2. **SDK parity** — `Dataset` covers ~12 of 45 commands; add `join`, `diff`, `uniq`/`frequency`, `validate`, `schema` (sdk spec promises CLI-mirroring).
3. **MCP tool expansion** — 14 tools today, none for diff/join/package/pipeline; agents get ~30% of capabilities.
4. **Data-quality report command** — combine `validate` + `stats` into one HTML/markdown report; both engines already exist, natural adjacency.
5. **Spec the unspecced surface** — `repack`, `uniq`, `flatten`, `split`, `apply`, `schema-bulk`, `join`, `fmt`, `sniff`, the entire `ai` sub-app, `mcp`, `formats` have no spec coverage.
6. **Split `cli/data_commands.py`** (3,692 lines, 32% of all mypy errors) into per-command modules — refactor enabling everything above.

## Phase 5 — Documentation & Repo Hygiene

| # | Item | Where | Effort |
|---|---|---|---|
| 5.1 | Fix WORKFLOW_GUIDE.md — example section cites archived `optimize-stats-command-duckdb` as "waiting for approval" | `WORKFLOW_GUIDE.md:15-21,40,54,118-131` | S |
| 5.2 | Fix openwiki drift — drop removed `query` command, add `config` sub-app | `openwiki/quickstart.md:34,46` | S |
| 5.3 | Update AGENTS.md structure tree — missing `undatum/cli/`, `mcp/`, `tui/`, `web/`, `tools/`, `recipes/` | `AGENTS.md:60-110` | S |
| 5.4 | OpenSpec hygiene — delete/relocate stale `changes/SCHEMA_IMPROVEMENTS_SUMMARY.md` + `PROPOSAL_STATUS_SUMMARY.md`; archive completed `add-undatum-improvement-roadmap` (all tasks done, 3 explicitly deferred) | `openspec/changes/` | S |
| 5.5 | Enforce docstring standard — enable ruff `D` rules (Google) scoped to `undatum/cmds/`, or relax CONTRIBUTING.md; sprint on worst offenders: `extractor.py` (1/19 docstringed), `api.py` (5/41), `doc.py` (5/27), `packager.py` (4/22) | ~40% have any docstring, 0% have `Example:` | M |
| 5.6 | README badges (PyPI, CI, py-versions); docs site gains development/architecture + testing pages (distill from openwiki), recipes catalog page, SDK API reference (Dataset/StatsResult/QueryResult); cross-link openwiki ↔ site | User docs are strong; dev docs thin | M |
| 5.7 | Fix stale package metadata — `pip show` reports 1.5.0 vs runtime 1.7.0 in `.venv`; reinstall editable | Cosmetic but confusing | S |

---

## Suggested Sequencing

```
Week 1   Phase 0 (0.1–0.5)                      → release v1.7.1
Week 2   Phase 1.1–1.3, 1.5 (gates + baseline)  → CI enforces ruff/black/coverage
Week 3–4 Phase 2.1–2.6 (UX coherence, specs)    → candidate v1.8.0
Ongoing  Phase 1.4, 1.7, 2.7 (mypy ratchet, deprecations, error handling)
Next     Phase 3 (test depth) in parallel with Phase 4 proposals
Backg.   Phase 5 (docs/hygiene) — batch into one docs PR
```

**OpenSpec routing:** Phases 0, 1.1–1.3, 2.1–2.2, 2.5–2.6, 3, 5 are direct fixes/chores. Phase 1.6 (extras reshuffle), Phase 2.3–2.4 (command deprecation), and all of Phase 4 are proposal-worthy per `openspec/AGENTS.md` (breaking/feature changes).

## Sources

- Feature inventory & spec/doc/UX audit — `undatum/core.py`, `undatum/cli/*.py`, `undatum/cmds/*.py`, `openspec/specs/`, `docs/docs/commands/`
- Code quality — `ruff check`, `black --check`, `mypy`, `pylint --enable=E` on 148 source files (36,819 lines)
- Tests — full `pytest` run in `.venv` (py3.13): 1152 collected, 1131 passed, 21 skipped, 18.1 s
- Documentation — README.md, docs/ (81 md files), CHANGELOG.md, openwiki/, CONTRIBUTING.md, WORKFLOW_GUIDE.md, openspec/changes/
