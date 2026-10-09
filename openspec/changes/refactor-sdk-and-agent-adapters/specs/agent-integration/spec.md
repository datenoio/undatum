## ADDED Requirements

### Requirement: Tools Generated From the Operation Registry
MCP and LangChain tools SHALL be generated from the operation registry with input schemas derived
from operation configs, so that every registered operation is available to agents unless it is
explicitly excluded.

#### Scenario: New operation becomes a tool
- **WHEN** a new operation is registered
- **THEN** `undatum mcp tools` lists a tool for it with a JSON Schema for its parameters

#### Scenario: Writing tools stay gated
- **WHEN** an agent calls a generated tool that writes a file without `confirm=true`
- **THEN** the tool returns `confirmation_required` and writes nothing

### Requirement: Tool Parity Reporting
The CLI SHALL report which CLI commands have no agent tool equivalent.

#### Scenario: Parity report
- **WHEN** user runs `undatum mcp tools --parity`
- **THEN** the output lists each command with its tool name or the reason it is excluded
