<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# undatum — Agent Guide

undatum is a Python CLI (and SDK) for converting, inspecting, validating and transforming
data files. It reads and writes through [iterabledata](https://github.com/datenoio/iterabledata)
and uses DuckDB for SQL and accelerated statistics. Python 3.10+, MIT, repository
https://github.com/datenoio/undatum (default branch `master`).

## Where things are

- Contributor docs: [`docs/docs/development/`](docs/docs/development/) — start with
  [architecture](docs/docs/development/architecture.md) (layers, read/write paths, where to
  look) and [testing](docs/docs/development/testing.md) (local checks, CI jobs).
- User docs: [`docs/docs/`](docs/docs/) (Docusaurus, published at https://datenoio.github.io/undatum/).
- Specs and change proposals: [`openspec/`](openspec/) — read `openspec/AGENTS.md` for the workflow.
- Package layout: `undatum/cli/` (Typer wrappers) → `undatum/cmds/` (implementations) →
  `undatum/common/` (shared readers, writers, errors); optional features in `undatum/ai/`,
  `mcp/`, `tools/`, `tui/`, `web/`, `sdk/`.

## Commands

```bash
make install-dev      # pip install -e ".[dev]"
make check-all        # ruff format check, ruff lint, mypy ratchet, pytest
pytest tests/test_converter.py -v
python scripts/generate_cli_reference.py   # after changing CLI options or help
python scripts/generate_sdk_reference.py   # after changing SDK docstrings/signatures
python scripts/generate_result_schemas.py  # after changing JSON result layouts
python scripts/run_doc_examples.py docs/docs/commands/head.md
```

Run mypy (`make type-check`) with Python 3.10.

## Conventions

- **Formatting and lint:** `ruff format` and `ruff check` (line length 100). Google-style
  docstrings; enforced for `undatum/cmds/` and `undatum/sdk/`.
- **Types:** `undatum/common/` is fully annotated; elsewhere the mypy error count per file may
  only go down (`mypy-baseline.json`).
- **CLI options:** use the shared names — `--format-in`/`-F`, `--format-out`/`-O`,
  `--output`/`-o`, `--limit`/`-n`, `--fields`/`-f`, `--delimiter`/`-d`, `--engine`/`-e`
  (`auto|duckdb|python`). They are enforced in `undatum/cli/conventions.py`.
- **Output:** write records with `emit_records()` / `RecordSink` from
  `undatum/common/writer.py` (any writable format, atomic files, stdout in the input's
  format). Do not open output files by hand.
- **JSON output:** informational commands print `undatum.common.results` documents
  (`emit()`); add or change a layout in `SCHEMAS` and bump its version on incompatible changes.
- **Errors:** raise subclasses of `UndatumError` (`undatum/common/errors.py`); they map to
  exit codes 1 (user error), 2 (configuration or missing dependency), 3 (system or
  database), 4 (internal), 130 (interrupted).
- **Optional dependencies:** import inside the function that needs them and raise
  `DependencyError` with the `pip install "undatum[extra]"` hint. Every dependency in
  `pyproject.toml` needs lower and upper bounds.
- **Data models:** use `dataclasses`, not pydantic, for new configuration and operation models.
- **Changelog:** user-visible changes go to `CHANGELOG.md` under Unreleased; commits use
  Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`).
- **Proposals:** new capabilities, breaking changes and architecture work start as an
  OpenSpec change in `openspec/changes/` (validate with `openspec validate <id> --strict`).

## Security notes

- No secrets in code; AI provider keys come from the environment.
- The Data API and MCP server are read-only; MCP file access is sandboxed to `--root`.
- Validation rule conditions use the restricted evaluator in `undatum/common/safe_expr.py` —
  never `eval`.
