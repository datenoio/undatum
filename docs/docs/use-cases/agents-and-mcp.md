---
title: "Agents and MCP"
description: "Give LLM agents controlled undatum tools"
---
# Agents and MCP

Give agents controlled dataset tools or add AI assistance to documentation.

## Connect undatum to an MCP client

```bash norun
pip install "undatum[mcp]"
undatum mcp tools
undatum mcp serve
```

Add this to Cursor `mcp.json` or Claude Desktop MCP settings:

```json
{
  "mcpServers": {
    "undatum": {
      "command": "undatum",
      "args": ["mcp", "serve"]
    }
  }
}
```

Every data operation is a tool (`dedup`, `join`, `rename`, `where`, ...): without
`output_path` it returns records inline, and writing a file requires `confirm=true`. Paths stay
inside the server's `--root`. `undatum mcp tools --parity` shows which CLI commands have a
tool. Full catalog and flags: [MCP](/integrations/mcp) and [`mcp`](/commands/mcp).

## Let the client browse datasets

The server also lists the data files under its root as resources (`undatum://datasets`, each
file's schema and sample) and offers ready prompts: `profile-dataset`,
`draft-validation-rules`, `plan-conversion` and `document-dataset`. See
[resources and prompts](/integrations/mcp#resources-and-prompts).

## Same results for scripts and agents

Informational commands print the same versioned JSON documents that the agent tools return:

```bash
undatum count data.csv --json
undatum sniff data.csv --json
undatum headers data.csv --json
```

See [JSON output](/commands/json-output).

## Describe the CLI to an agent

Agents that run shell commands can read the whole command line as data instead of `--help` text:

```bash
# Every command with its arguments, options, engines and JSON layouts (undatum.commands/1)
undatum commands --json

# One tool definition per command, with JSON Schema parameters
undatum commands --tools

# Find the command for a task
undatum commands --search "remove duplicate"
```

`undatum.cli.manifest.tool_argv()` turns a tool call into the command line. See
[`commands`](/commands/commands).

## Generate assisted dataset documentation

```bash
undatum ai doc data.csv --format-out json --blocks general,schema,quality
```

## Python tools without MCP

```python
from undatum import tools
from undatum.tools import schemas

print(tools.detect_format("data.csv"))
print(schemas.call_tool("query_sql", {"path": "data.csv", "query": "SELECT * FROM data LIMIT 5"}))
print(schemas.to_openai_functions())
```

See [MCP](/integrations/mcp), [AI documentation](/integrations/ai), [`ai`](/commands/ai), and the [Python SDK](/integrations/sdk).
