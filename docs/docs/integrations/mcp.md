---
title: "MCP and agent tools"
description: "JSON tools, LangChain, and the MCP stdio server"
---
# AI agent tools and MCP server

undatum exposes its operations to LLM agents through a JSON tool layer that builds
on iterabledata's foundation tools and adds undatum-specific tools (ad-hoc DuckDB
SQL, value frequency, and confirm-gated dedup/mask/sample).

### JSON tools and function-calling schemas

```python
from undatum import tools
from undatum.tools import schemas

# Call a tool directly (returns {"ok": ..., "data"/"error": ...})
result = tools.detect_format("data.csv")
freq = tools.frequency("data.csv", "country")
freq = tools.frequency("nested.jsonl", "capital_city.lat", flatten_nested=True)

# Dispatch by name (handy for agent runtimes)
schemas.call_tool("query_sql", {"path": "data.parquet", "query": "SELECT * FROM data LIMIT 5"})

# Export schemas for LLM function calling
openai_fns = schemas.to_openai_functions()
anthropic_tools = schemas.to_anthropic_tools()
```

Tools that write (`convert_file`, `deduplicate`, `mask_fields`, `sample_data`, and every operation
tool given an `output_path`) require `confirm=True` to prevent accidental writes. Pass `flatten_nested=True` to unfold nested fields
onto dotted paths (same as `--flatten-nested` on the CLI).

### Tool catalog

Foundation tools (from iterabledata) plus undatum extras. `undatum mcp tools` prints the live list.

| Tool | Writes? | Notes |
|------|---------|--------|
| `detect_format` | no | Format and compression for a path |
| `describe_capabilities` | no | Catalog metadata for a format id |
| `read_sample` | no | Bounded sample; optional `redact` |
| `infer_schema` | no | Inferred schema |
| `analyze_dataset` | no | Structure; optional `autodoc` |
| `compute_stats` | no | Column statistics |
| `convert_file` | yes | Requires `confirm=true`; `dry_run` available |
| `generate_documentation` | no | AI dataset documentation |
| `validate_data` | no | Field rules; default mode `stats` |
| `plan_conversion` | no | Declarative convert plan |
| `suggest_transform` | no | Natural-language transform spec |
| `translate_filter` | no | Filter expression → AST |
| `query_sql` | no | DuckDB SQL; file registered as view `data` |
| `frequency` | no | Value counts; optional `table`, `flatten_nested` |
| `deduplicate` | yes | Requires `confirm=true` |
| `mask_fields` | yes | Requires `confirm=true` |
| `sample_data` | yes | Requires `confirm=true` |
| `count_records` | no | `undatum.count/1` document, same as `undatum count --json` |
| `list_fields` | no | `undatum.headers/1`: field names in file order |
| `sniff_file` | no | `undatum.sniff/1`: format, compression, encoding, delimiter, fields, count |
| `diff_files` | no | `undatum.diff/1`; `key`, `ignore_order`, `summary_only`, `limit` per list |

The four informational tools return the same documents as the CLI's `--json` output (see
[JSON output](/commands/json-output)), so a script and an agent read identical results.

### Operation tools

Every data operation of the CLI's operation registry is also a tool, named like the command:
`cat`, `dedup`, `enum`, `exclude`, `explode`, `fill`, `fixlengths`, `head`, `join`, `mask`,
`rename`, `replace`, `reverse`, `sample`, `search`, `select`, `slice`, `sort`, `tail`,
`transpose`. Their parameters are generated from the operation's configuration, so a new
operation becomes a tool automatically.

- `input_path` (required) plus the operation's options, e.g. `dedup(keys=["id"], keep="last")`.
- Without `output_path` the tool is read-only and returns up to `limit` records (default 100) with
  `truncated` telling whether there were more.
- With `output_path` it writes the full result in the format of the extension, and needs
  `confirm=true`.
- Other inputs are paths too: `join(right_path=...)`, `exclude(exclude_path=...)`,
  `cat(others_paths=[...])`; they are checked against the sandbox like `input_path`.
- `format_in`, `table` and `flatten_nested` set how the inputs are read.

`undatum mcp tools --parity` lists every CLI command with the tool that covers it, or why none
does.

### LangChain

```python
from undatum.tools.langchain import get_tools  # pip install "undatum[langchain]"

lc_tools = get_tools()  # list[StructuredTool] with JSON Schema arguments; paths confined to the current directory
lc_tools = get_tools(root="./data")  # or confine them to another directory
```

### MCP server

Expose the tools to MCP-compatible agents (Claude Desktop, Cursor, etc.) over stdio:

```bash norun
pip install "undatum[mcp]"

# List the tools the server exposes
undatum mcp tools

# Run the stdio server (wire this command into your MCP client)
undatum mcp serve

# Standalone console entry point (equivalent)
undatum-mcp
```

Copy-paste client config (Cursor `mcp.json` and Claude Desktop) is on the [`mcp`](/commands/mcp) command page.

### Resources and prompts

Besides tools, the server offers **resources** that a client can show or attach without a
tool call, and **prompts** (ready plans that use the tools):

| Resource | Content (JSON) |
|----------|----------------|
| `undatum://datasets` | data files under the root (at most 500, 4 levels deep): path, format, compression, size, links to their schema and sample |
| `undatum://dataset/{path}/schema` | fields with inferred types and nullability (from up to 10,000 records) |
| `undatum://dataset/{path}/sample` | the first 20 records |
| `undatum://formats` | supported formats and whether undatum can write them |

`{path}` is relative to the server root with `/` percent-encoded:
`undatum://dataset/exports%2F2026.csv/schema`. Paths outside the root are refused, like tool
paths.

| Prompt | Arguments | What it asks the model to do |
|--------|-----------|------------------------------|
| `profile-dataset` | `path` | profile every field and name the main quality issues |
| `draft-validation-rules` | `path` | write a rule file using the [built-in rules](/commands/validate-rules) |
| `plan-conversion` | `path`, `target_format` | plan a conversion and ask before running it |
| `document-dataset` | `path` | write Markdown documentation |

In Claude Desktop or Cursor, resources appear in the attachment menu and prompts as slash
commands once the server is configured (see [MCP server](#mcp-server)):

```json norun
{
  "mcpServers": {
    "undatum": {
      "command": "undatum",
      "args": ["mcp", "serve", "--root", "/path/to/data"]
    }
  }
}
```

### Security model

An agent may follow instructions hidden in the data it reads, so the tools are sandboxed:

- **Filesystem root.** Every path argument (`path`, `input_path`, `output_path`, `source`,
  `target`, and any `*_path` / `*_paths` argument) must resolve inside the root directory — `--root` for `undatum mcp serve`, `root=`
  for `get_tools()`, the current directory by default. `../`, absolute paths outside the root and
  symlinks that point outside are rejected with `path_outside_root`; remote URIs (`s3://`, ...)
  with `remote_uri_not_allowed`.
- **Read-only SQL.** `query_sql` accepts exactly one `SELECT` (or `WITH ... SELECT`) statement.
  The DuckDB connection is restricted to the root directory (`enable_external_access=false`,
  `allowed_directories`, locked configuration), so `read_text('/etc/passwd')`, `COPY ... TO`,
  `ATTACH` and `INSTALL` fail.
- **Writes need confirmation.** `convert_file`, `deduplicate`, `mask_fields`, `sample_data` and
  operation tools with an `output_path` write nothing unless called with `confirm=true`.

`undatum mcp serve --allow-anywhere` (or `get_tools(allow_anywhere=True)`) turns the filesystem
sandbox off. Use it only for trusted local work.

See also the [`mcp`](/commands/mcp) command.
