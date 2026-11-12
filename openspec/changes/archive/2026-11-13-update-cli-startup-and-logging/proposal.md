# Change: Fast CLI Startup and Quiet Default Logging

## Why
`undatum --version` takes 0.8 s and `import undatum.core` 0.68 s because `undatum/core.py`
eagerly imports every command module, which pulls in pandas, the legacy AI providers, the Data
API and plotter. A 10-row `head` uses 216 MB RSS before doing any work. `undatum/__main__.py:19`
configures the root logger at INFO with timestamps, so every command prints lines such as
`2026-10-07 09:34:54,248 - root - INFO - File filetype csv and compression raw` to stderr.
`--verbose` is declared separately on 74 commands. Plugins are discovered and imported on every
start, even for `--version`.

## What Changes
- Split `undatum/cli/data_commands.py` (3 692 lines, 50 commands) into per-command modules.
- Lazy command loading: command modules and heavy libraries (pandas, duckdb, pyarrow, matplotlib,
  fastapi) are imported when the command runs (Click lazy group or in-function imports).
- Startup budget: `undatum --help` and `--version` ≤ 0.3 s on the reference CI runner (0.13–0.18 s
  measured locally), and
  `import undatum.core` MUST NOT import pandas, duckdb or pyarrow (checked in CI).
- Logging: default level WARNING on the `undatum` logger (not root), message-only format; global
  `-v` (INFO), `-vv` (DEBUG), `-q` (errors only); per-command `--verbose` stays as an alias.
- Plugins: a new `undatum.commands` entry point group registers plugin commands that are imported
  only when they run (or help is rendered); legacy `undatum.plugins` plugins keep loading at start.

## Impact
- Affected specs: `cli-conventions`
- Affected code: `undatum/__main__.py`, `undatum/core.py`, `undatum/cli/*.py` (new `undatum/cli/commands/`),
  `undatum/plugins/manager.py`, logging calls that use `logging.info(...)` on the root logger
