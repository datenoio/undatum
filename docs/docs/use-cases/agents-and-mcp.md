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

Write tools require `confirm=true`. Full catalog and flags: [MCP](/integrations/mcp) and [`mcp`](/commands/mcp).

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
