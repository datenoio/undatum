---
title: "Testing"
description: "Test layout, local checks and what CI runs"
---
# Testing

## Layout

- `tests/test_*.py` — unit and CLI tests (`typer.testing.CliRunner` or subprocesses).
- `tests/conftest.py` — fixtures (`sample_csv_file`, `sample_jsonl_file`, `semicolon_csv`,
  `benchmark`). A test module that needs other sample rows sets `SAMPLE_CSV` or `SAMPLE_JSONL`
  at module level instead of redefining the fixture.
- `tests/integration/` — `@pytest.mark.integration` tests against live PostgreSQL, MySQL,
  MongoDB and Elasticsearch servers (CI starts them as services; skipped locally unless the
  connection environment variables are set).
- `tests/benchmarks/` — benchmark harness tests, `budgets.toml`, and the memory budget tests
  (`UNDATUM_MEMORY_TESTS=1`); see [Benchmarks](./benchmarks.md).
- Tests for optional extras (`api`, `mcp`, `tui`, `web`, ...) skip when the extra is missing.

## Local checks

```bash norun
make install-dev        # pip install -e ".[dev]"
make check-all          # format check, lint, type check, tests
pytest tests/test_converter.py -v
make test-cov
```

| Command | What it checks |
|---------|----------------|
| `make format-check` | `ruff format --check` |
| `make lint` | `ruff check` (incl. pylint and docstring rules) and dependency version bounds |
| `make type-check` | mypy ratchet — run it with Python 3.10 |
| `make type-baseline` | lock in fixed type errors (`mypy-baseline.json` may only shrink) |
| `python scripts/mypy_ratchet.py --update --allow-moves` | record the baseline after moving code between files (the total may not grow) |
| `python scripts/generate_cli_reference.py` | regenerate the option tables on command pages |
| `python scripts/generate_sdk_reference.py` | regenerate the SDK reference |
| `python scripts/generate_result_schemas.py` | regenerate the JSON output layouts and schema files (after changing `undatum/common/results.py`) |
| `python scripts/run_doc_examples.py` | run every shell example in the docs |
| `make bench` | time and memory of core commands on 100k rows against the budgets |

`tests/test_docs_commands.py` fails when a docs example uses an unknown command or option,
a deprecated spelling, or when the generated reference pages are stale.

## Documentation examples

`scripts/run_doc_examples.py` runs every `undatum` line of every ```bash block in
`docs/docs/` inside a sandbox populated with fixture files (`data.csv`, `data.jsonl`,
`nested.jsonl`, `workbook.xlsx`, `data.parquet`, `rules.yml`, a SQLite `db.db`, ...).
Examples that need a database server, cloud storage, an AI provider or network access, or
that start a server, go in a block marked `norun`:

````markdown
```bash norun
undatum db query "SELECT 1" --db postgresql://user:pass@host/db
```
````

## CI

`.github/workflows/ci.yml` runs on pushes and pull requests to `master`:

| Job | What it does |
|-----|--------------|
| lint | ruff lint and format, tool versions in sync, dependency bounds, `uv.lock` up to date |
| type-check | mypy ratchet on Python 3.10 |
| test | pytest on Python 3.10–3.13 from `uv.lock`, coverage at least 65% (80% on changed lines) |
| lowest-dependencies | tests with every direct dependency at its lower bound |
| memory-budget | row commands stay under 300 MB for 1M rows and do not grow with the input |
| base-install | wheel without extras: every core module imports; install footprint |
| install-gate | clean wheel install smoke test |
| deprecations | `DeprecationWarning` raised by undatum code is an error |
| db-integration | integration tests against database services |
| docs | Docusaurus build |
| doc-examples | every shell example in `docs/docs` against fixtures |
| audit | `pip-audit` (advisory) |

`.github/workflows/benchmarks.yml` compares wall time and memory with the base branch on pull
requests and records a 1M-row history when started by hand ([Benchmarks](./benchmarks.md)).

Release builds (`release.yml`) require the same tests, a clean install and the binaries to
pass before anything is published.

## When you change a command

1. Run its `tests/test_*.py` and `tests/test_cli_conventions.py`.
2. Regenerate the reference if options or help changed.
3. Run the examples of its page: `python scripts/run_doc_examples.py docs/docs/commands/<name>.md`.
