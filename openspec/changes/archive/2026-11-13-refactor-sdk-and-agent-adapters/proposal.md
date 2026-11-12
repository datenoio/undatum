# Change: Build SDK and Agent Tools on the Operation Registry

## Why
The SDK `Dataset` (`undatum/sdk/dataset.py`) runs each chained step through a CLI command class
that writes a full temporary JSONL file, so every step re-serializes the whole dataset, loses
types (dates, decimals, nested values become JSON) and leaks disk space. MCP/LangChain tools
(`undatum/tools/_core.py`, `undatum/mcp/server.py`) re-implement parts of commands and expose 17 of
80 commands; the SDK covers about 20 operations. The three surfaces drift because each is written
by hand.

## What Changes
- SDK builds a lazy plan: `Dataset.read(...)` and transform methods append operations; execution
  happens on `write()`, iteration, `count()`, `stats()` or conversion to pandas/polars, streaming
  records through the operation registry (or a DuckDB relation chain when every step has SQL).
- No intermediate files between SDK steps; Python values keep their types between steps.
- SDK methods and MCP/LangChain tool schemas are generated from operation configs (pydantic models
  give JSON Schema for tools); write tools keep the `confirm=True` gate and the sandbox from
  `update-security-hardening`.
- A parity report (`undatum mcp tools --parity`) lists operations not exposed to agents.

## Impact
- Affected specs: `sdk`, `agent-integration` (new)
- Affected code: `undatum/sdk/`, `undatum/tools/`, `undatum/mcp/server.py`, `undatum/cli/mcp_cli.py`
- Depends on: `refactor-streaming-operations-core`
