## ADDED Requirements

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
