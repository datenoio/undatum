# agent-integration Specification

## Purpose
Expose undatum to AI agents: MCP and agent tools generated from the operation registry, tool parity reporting, and MCP dataset resources and prompt templates.
## Requirements
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

### Requirement: MCP Dataset Resources
The MCP server SHALL expose the datasets inside its sandbox root, their schemas and bounded
samples as MCP resources.

#### Scenario: List datasets
- **WHEN** an MCP client reads `undatum://datasets`
- **THEN** it receives each file under the sandbox root with detected format and size

#### Scenario: Bounded sample
- **WHEN** an MCP client reads `undatum://dataset/data.csv/sample`
- **THEN** it receives at most the configured number of rows

### Requirement: MCP Prompt Templates
The MCP server SHALL provide prompt templates for profiling a dataset, drafting validation rules,
planning a conversion and documenting a dataset.

#### Scenario: Draft validation rules prompt
- **WHEN** an MCP client requests the `draft-validation-rules` prompt for `customers.csv`
- **THEN** the prompt includes the dataset schema and sample and asks for a rules file in the
  documented YAML format

