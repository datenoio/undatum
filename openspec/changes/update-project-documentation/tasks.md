## 1. Fix drift now
- [x] 1.1 Correct README claims (streaming scope, output formats, CI, binaries) until fixes land
- [x] 1.2 Fix `openwiki/quickstart.md:34`, `AGENTS.md:60-110`, `AGENTS.md:310`, WORKFLOW_GUIDE.md

## 2. Generated reference
- [x] 2.1 Script that renders command reference pages from the Click tree into `docs/docs/commands/`
- [x] 2.2 CI check: regenerate and fail on diff
- [x] 2.3 Capability line per command (formats in/out, streaming, engines) from command metadata
- [x] 2.4 SDK API reference from docstrings; docstring coverage for `undatum/sdk/` = 100%

## 3. Executable docs
- [x] 3.1 Extract `bash` blocks from `docs/docs/**/*.md`, run them in a fixture sandbox in CI
- [x] 3.2 Mark intentionally non-runnable examples with an explicit annotation

## 4. Consolidation
- [x] 4.1 Move architecture/testing content from `openwiki/` into `docs/docs/development/`
- [x] 4.2 Shrink AGENTS.md to essentials plus links
- [x] 4.3 Single source for OpenSpec agent prompts with a generator for tool-specific copies
- [ ] 4.4 File GitHub issues for open items in `dev/docs/*`; move reports to `dev/docs/archive/`
- [x] 4.5 Add README badges
