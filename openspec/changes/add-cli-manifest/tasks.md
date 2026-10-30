## 1. Manifest
- [x] 1.1 Walk the visible commands of the Click tree in `undatum/cli/manifest.py`; the CLI
      reference generator uses the same walk
- [x] 1.2 Describe arguments and options (flags, JSON type, choices, default, required,
      repeatable, deprecated spellings), engines, capabilities, result schema and examples
- [x] 1.3 Register the `undatum.commands/1` result layout and the exit-code table

## 2. Command
- [x] 2.1 `undatum commands [WORDS]... [--search TEXT] [--json | --tools]`
- [x] 2.2 Tool definitions with JSON Schema parameters; `tool_argv()` builds the command line

## 3. Tests and documentation
- [x] 3.1 Every command appears; tool calls round-trip through `tool_argv()` and Click parsing
- [x] 3.2 Command page, agents guide, CLI reference, result schemas, CHANGELOG
