# Change: Consolidate Documentation and Keep It in Sync with the CLI

## Why
User documentation is strong (81 Docusaurus pages, 57 command pages), but the project is described
in seven places — README, `docs/`, `openwiki/`, `openspec/`, `dev/docs/` (14 reports, 7 411 lines),
AGENTS.md/WORKFLOW_GUIDE.md/CONTRIBUTING.md and three copies of OpenSpec agent prompts
(`.agent/`, `.amazonq/`, `.cursor/`) — and several claims contradict the code:
- "Low memory footprint: streams data" while ~15 commands hold the whole dataset in memory;
- output in any of 145 formats while transforms write only csv/json/jsonl/bson;
- "CI tests 3.9–3.13" while CI never runs and 3.9 cannot import the package;
- release binaries that v1.7.0 does not have;
- `openwiki/quickstart.md:34` lists `query` and `filter` commands that do not exist;
- `AGENTS.md:60-110` omits `cli/`, `mcp/`, `tui/`, `web/`, `tools/`, `recipes/`;
- `AGENTS.md:310` says "CI targets `main`" while the default branch is `master`.
Review reports in `dev/docs/` accumulate without becoming tracked work. Only ~40% of functions
have docstrings and there is no SDK API reference.

## What Changes
- Two sources: the Docusaurus site for users and a "Development" section on the same site for
  contributors (architecture and testing distilled from `openwiki/`); AGENTS.md becomes a short
  pointer; `openwiki/` is retired or generated.
- CLI reference pages are generated from the Click command tree (options, types, defaults,
  aliases) and a CI check fails when they are stale.
- Every `bash` example in the docs is executed in CI against fixtures (doc tests).
- Each command page shows a capability line: input formats, output formats, streaming yes/no,
  engines.
- SDK API reference generated from docstrings (`Dataset`, `StatsResult`, `QueryResult`).
- README badges (PyPI, CI, Python versions) and honest feature claims.
- Open items from `dev/docs/*` reviews become GitHub issues; the reports move to
  `dev/docs/archive/`.
- One source for OpenSpec agent prompts, generated into `.agent/`, `.amazonq/`, `.cursor/`.

## Impact
- Affected specs: `documentation`
- Affected code: `docs/`, `scripts/` (generators), `README.md`, `AGENTS.md`, `openwiki/`,
  `WORKFLOW_GUIDE.md`, `dev/docs/`, `.agent/`, `.amazonq/`, `.cursor/`, CI docs job
