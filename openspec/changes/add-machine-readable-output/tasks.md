## 1. Result models
- [x] 1.1 Define pydantic result models with schema ids for each informational command
      (dataclass `ResultSchema` registry in `undatum/common/results.py`, not pydantic)
- [x] 1.2 Reuse them in SDK results and MCP tools
      (agent/MCP tools `count_records`, `list_fields`, `sniff_file`, `diff_files` return the CLI
      documents; SDK methods keep returning Python values)

## 2. CLI
- [x] 2.1 Add `--format-out json` / `--json` to count, headers, sniff, stats, schema, frequency,
      uniq, diff, validate, formats, config show, analyze
- [x] 2.2 JSON error envelope on stderr in JSON mode

## 3. Tests and docs
- [x] 3.1 Snapshot tests per schema; publish schemas on the docs site
