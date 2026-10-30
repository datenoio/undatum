# Change: Machine-Readable Description of the CLI (`undatum commands`)

## Why
undatum has 62 commands. Agents and scripts learn them from `--help` text, which is meant for
people. The MCP server describes its own tools (`undatum mcp tools --json`), but not the CLI.
Tools like qsv export tool definitions for every command, so an agent can call the CLI directly.
The pieces exist already: the Click command tree, the capability table
(`undatum/cli/capabilities.py`) and the versioned result schemas (`undatum/common/results.py`).
This is item 19 ("export tool descriptions") of the October 2026 engine review
(`analysis/2026-10-28-undatum-engines-and-competitors.md`, section 6.3).

## What Changes
- **New command `undatum commands [WORDS]...`:** lists the commands with their one-line
  summaries. The words narrow the list to a command or group (`undatum commands db`).
  - `--search TEXT` keeps the commands whose name, summary or help contains every word of `TEXT`.
- **`--json`:** prints the manifest, a `undatum.commands/1` document, generated from the Click
  tree at run time, so plugin commands are included. It has the undatum version, the exit codes,
  the command groups, and for every visible command:
  - name, summary, help and examples;
  - usage, arguments and options: flags, type, choices, default, required, repeatable,
    deprecated spellings;
  - the engines, the capability line, and the result schema its JSON output follows.
- **`--tools`:** prints one tool definition per command (`name`, `description`, `parameters` as
  JSON Schema), in the shape `undatum mcp tools --json` uses.
  - Properties are named after the long option (`--format-in` is `format_in`).
  - `undatum.cli.manifest.tool_argv()` turns a tool call back into the command line.
- **Refactor:** `scripts/generate_cli_reference.py` walks the command tree through the same module.

## Impact
- Affected specs: `cli-introspection` (new).
- Affected code: `undatum/cli/manifest.py`, `undatum/cli/manifest_cli.py`, `undatum/core.py`,
  `undatum/common/results.py`, `undatum/common/errors.py`, `scripts/generate_cli_reference.py`,
  tests and documentation.
