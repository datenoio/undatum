## 1. SDK
- [x] 1.1 Implement the immutable plan (`SourceSpec`, `OperationCall`) and executors
- [x] 1.2 Re-implement existing `Dataset` methods on the plan; keep signatures
- [x] 1.3 Remove temp-file chaining; tests for type preservation (date, Decimal, nested dict)
- [x] 1.4 Generate missing SDK methods for registry operations (`join`, `diff`, `uniq`,
      `frequency`, `validate`, `schema`) — added `uniq`, `frequency`, `validate`, `schema` and
      methods for every registry operation; `diff` follows when it becomes an operation
- [x] 1.5 Fully annotate `undatum/sdk/` and add it to the strict mypy override next to
      `undatum.common.*`

## 2. Agent tools
- [x] 2.1 Generate MCP and LangChain tools from the registry with JSON Schema inputs
- [x] 2.2 Keep confirm gate and sandbox for writing tools
- [x] 2.3 `undatum mcp tools --parity` report; CI prints the parity table
- [x] 2.4 Port the MCP server to the mcp 2.x API (`FastMCP` became
      `mcp.server.mcpserver.MCPServer`) and lift the `mcp<2` cap in the `mcp` extra

## 3. Docs
- [x] 3.1 Update `docs/docs/integrations/sdk.md` and `mcp.md` with lazy semantics and tool list
