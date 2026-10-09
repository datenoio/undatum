## 1. Shared option types
- [x] 1.1 Create `undatum/cli/options.py` with Annotated types for every row in the design table
      (implemented as `undatum/cli/conventions.py`, applied to the built command tree by the root
      group, so every command and plugin follows the table without per-declaration edits)
- [x] 1.2 Implement the deprecated-alias callback with a single warning per invocation
- [x] 1.3 Switch `--engine` to `click.Choice` with the `iterable` → `python` mapping

## 2. Apply to commands
- [x] 2.1 Replace inline declarations in `undatum/cli/data_commands.py` and other `cli/` modules
- [x] 2.2 Add short flags; resolve per-command collisions
- [x] 2.3 Hide `profile`, `document`, `ingest` from `--help` as aliases of `stats`, `doc`, `db load`
- [x] 2.4 Make `--autodoc` delegate to the `ai doc` implementation (done in `remove-legacy-ai-stack`)

## 3. Guardrails and docs
- [x] 3.1 Add a Click-tree test: visible option names ⊂ canonical vocabulary + documented
      command-specific options; short flags unique per command
- [x] 3.2 Update `docs/docs/commands/shared-options.md`, command pages, recipes and templates
- [x] 3.3 CHANGELOG: list every deprecated spelling and its replacement
