## ADDED Requirements

### Requirement: CLI Manifest
undatum SHALL describe its command-line interface as data with `undatum commands --json`. The
manifest SHALL be a `undatum.commands/1` document generated from the command tree at run time,
so it includes plugin commands and never disagrees with `--help`. For every visible command it
SHALL give:
- the name, summary, help text and examples;
- the arguments and options: flags, JSON type, choices, default, whether it is required or
  repeatable, and deprecated spellings;
- the engines, the capabilities, and the result schema its JSON output follows.

It SHALL also list the command groups and the exit codes.

#### Scenario: Agent reads the manifest
- **WHEN** a user runs `undatum commands --json`
- **THEN** the output is one `undatum.commands/1` document
- **AND** `count` lists `--format-in` with its short flag `-F` and the result schema `undatum.count/1`

#### Scenario: Narrowing the list
- **WHEN** a user runs `undatum commands db` or `undatum commands --search duplicate`
- **THEN** only the `db` commands, or the commands whose name, summary or help mention
  "duplicate", are listed

### Requirement: CLI Tool Definitions
`undatum commands --tools` SHALL print one tool definition per command: `name`, `description`
and `parameters` (JSON Schema), in the shape `undatum mcp tools --json` uses. Parameters SHALL
be named after the long option (`--format-in` is `format_in`) or after the argument.
`undatum.cli.manifest.tool_argv()` SHALL turn a tool call into the command line that runs it.

#### Scenario: Tool call becomes a command line
- **WHEN** an agent calls `undatum_count` with `{"input_file": "data.csv", "format_in": "csv"}`
- **THEN** `tool_argv()` returns `["count", "--format-in", "csv", "data.csv"]`
- **AND** an unknown parameter raises a user error naming it
