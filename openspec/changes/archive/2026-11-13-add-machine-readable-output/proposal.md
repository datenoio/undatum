# Change: JSON Output for Every Informational Command

## Why
Only 4 commands accept `--json`. Scripts and agents must parse rich tables to read the results of
`count`, `headers`, `sniff`, `stats`, `schema`, `frequency`, `uniq`, `diff`, `validate`, `formats`
and `config show`. The MCP tools return JSON, but the CLI does not, so behaviour diverges.

## What Changes
- Every command whose result is information rather than records accepts `--format-out json`
  (with `--json` as a shorthand), printing one JSON document to stdout and nothing else.
- Each result has a versioned, documented JSON schema (`"schema": "undatum.stats/1"`), published
  in the docs and tested with snapshot tests.
- Errors in JSON mode are also JSON on stderr (`{"error": {"code": ..., "message": ...}}`) with the
  usual exit codes.
- MCP tools reuse the same result models, so CLI and agent outputs match.

## Impact
- Affected specs: `cli-conventions`
- Affected code: informational commands in `undatum/cli/` and `undatum/cmds/`, result models in
  `undatum/sdk/results.py`, docs
