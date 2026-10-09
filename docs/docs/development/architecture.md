---
title: "Architecture"
description: "How undatum is put together: boot sequence, layers, read and write paths, where to look"
---
# Architecture

undatum is a thin CLI over two engines — [iterabledata](https://github.com/datenoio/iterabledata)
for streaming I/O and DuckDB for SQL and accelerated aggregates — exposed through several
surfaces that share the same command implementations.

## Surfaces

| Surface | Entry point | Notes |
|---------|-------------|-------|
| CLI | `undatum` / `data` (`undatum/__main__.py`) | Top-level data commands plus groups `ai`, `api`, `db`, `package`, `pipeline`, `formats`, `mcp`, `plugins`, `config`, `examples` |
| Python SDK | `undatum.Dataset` (`undatum/sdk/`) | Methods mirror the CLI transforms ([reference](/integrations/sdk-reference)) |
| Data API | `undatum api serve` (`undatum/cmds/api_app.py`) | Read-only FastAPI + DuckDB over files |
| MCP / agent tools | `undatum mcp serve`, `undatum.tools` | Read-only by default, sandboxed to `--root` |
| TUI / web | `undatum tui`, `undatum web` | Sampled explorers; `undatum/tui/services.py` has no Textual import so the web extra works without it |

## Boot sequence

1. `undatum.__main__.main()` sets quiet logging and runs the Typer app. It maps
   `UndatumError` subclasses and missing optional modules to the documented exit codes
   (0, 1, 2, 3, 4, 130) and treats a closed stdout pipe as success.
2. `undatum.core.app` is a Typer app whose group class, `UndatumGroup`:
   - imports command modules only when a command runs (start-up stays near 0.15 s);
   - loads plugin commands lazily from the `undatum.commands` entry point group;
   - applies the option conventions of `undatum/cli/conventions.py` to every command
     (canonical names, short flags, `--engine` choices, hidden deprecated spellings);
   - rewrites deprecated spellings with a warning before parsing;
   - replaces `-` inputs with a spooled copy of stdin and decides the stdout format
     (`undatum/common/stdio.py`);
   - runs each invocation in its own `contextvars` context so per-command state never
     leaks into the next call (tests, SDK).
3. The root callback handles `-v`/`-vv`/`-q`.

## Layers

- `undatum/cli/` — Typer wrappers: arguments, options and help text. They build an options
  dict and call a command class.
- `undatum/cmds/` — command implementations (one module per command family).
- `undatum/common/` — shared machinery, fully type-annotated: errors, readers
  (`s3_iterable.open_path`, `command_utils`), writers (`writer.py`), stdin/stdout
  (`stdio.py`), DuckDB configuration, engine selection, filters, progress bars, tables.
- `undatum/formats/`, `undatum/validate/`, `undatum/templates/`, `undatum/recipes/` —
  format helpers, validation rule sets, pipeline templates, example recipes.
- `undatum/ai/`, `undatum/mcp/`, `undatum/tools/`, `undatum/tui/`, `undatum/web/` — optional
  features, imported only when used.

## Read path

1. Path or URI → `open_path()`: local files and `gs://`/`az://`/`s3a://` go to iterabledata,
   `s3://` reads are downloaded with boto3 (region/profile), database URIs use
   iterabledata's drivers, other schemes can be handled by connector plugins.
2. Dialect: `--format-in`, `--table`/`--sheet`, `--delimiter` (auto-detected when omitted),
   `--quotechar`, `--encoding`.
3. Optional `--flatten-nested` projection, `--filter` (translated to a DuckDB `WHERE`
   when possible), and `--on-error raise|skip|warn` with `--error-log`.
4. Engine: `detect_engine()` picks DuckDB for formats it reads natively and the Python
   (iterabledata) engine otherwise; `--engine` overrides it.

## Write path

All record output goes through `undatum/common/writer.py`:

- `emit_records(records, output)` writes to a file (`write_records` → `RecordSink`) or to
  stdout (`StdoutSink`).
- Files are written to a temporary sibling and renamed on success; formats iterabledata
  cannot write fail before anything is created.
- On stdout the format is `--format-out`, else the input's text format (CSV, TSV, JSON,
  JSON Lines), else JSON Lines. Binary formats are refused on a terminal.
- DuckDB paths write with `COPY ... TO` (`duckdb_copy_to_file`).

## Configuration

`undatum config show` prints the merged `defaults:`. Precedence (later wins): `UNDATUM_*`
environment variables → `~/.undatum/config.yaml` → `./undatum.yaml` → CLI flags. Provider API
keys stay in the environment.

## Where to look

| Surface | Wrapper | Implementation |
|---------|---------|----------------|
| Data commands | `undatum/cli/commands/*.py` (shared options in `undatum/cli/options.py`) | `undatum/cmds/*.py` |
| Option conventions | `undatum/cli/conventions.py` | applied in `undatum/core.py` |
| Command capabilities (docs) | `undatum/cli/capabilities.py` | `scripts/generate_cli_reference.py` |
| AI | `undatum/cli/ai_cli.py` | `undatum/ai/`, iterabledata `iterable.ai` |
| Data API | `undatum/cli/api_cli.py` | `undatum/cmds/api.py`, `undatum/cmds/api_app.py` |
| Databases | `undatum/cli/db_cli.py` | `undatum/cmds/db_query.py`, `db_load.py`, `db_dump.py`, `undatum/cmds/ingester/` |
| Formats | `undatum/cli/formats_cli.py` | iterabledata capability catalog |
| Packages | `undatum/cli/package_cli.py` | `undatum/cmds/packager.py` |
| Pipelines | `undatum/cli/pipeline_cli.py` | `undatum/cmds/pipeline.py`, `undatum/common/pipeline_parser.py` |
| Plugins | `undatum/cli/plugins_cli.py` | `undatum/plugins/` |
| MCP | `undatum/cli/mcp_cli.py` | `undatum/mcp/server.py`, `undatum/tools/` (sandbox in `tools/sandbox.py`) |
| Validation rules | — | `undatum/common/validation_rules.py`, `undatum/common/safe_expr.py` |
| Errors and exit codes | — | `undatum/common/errors.py` |

## Changing a command

1. Find the wrapper in `undatum/cli/` and follow it into `undatum/cmds/`.
2. Read the matching `tests/test_*.py` first.
3. Write output through `emit_records`/`RecordSink` and raise `UndatumError` subclasses.
4. After changing options or help text, run `python scripts/generate_cli_reference.py`;
   after changing the SDK, `python scripts/generate_sdk_reference.py`.
5. Changes to behaviour or interfaces start with an OpenSpec proposal
   (`openspec/AGENTS.md`); bug fixes do not need one.

See [Testing](/development/testing) for what to run.
