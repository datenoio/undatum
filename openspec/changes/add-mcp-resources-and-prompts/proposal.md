# Change: MCP Resources and Prompts for Dataset Work

## Why
The MCP server exposes tools only. Agents work better when they can browse what is available
(datasets in the sandbox root, their schemas and samples) as MCP resources, and when common tasks
(profile a dataset, write a validation rules file, plan a conversion) are offered as MCP prompts
instead of being re-invented in every conversation.

## What Changes
- Resources: `undatum://datasets` (files in the sandbox root with detected format and size),
  `undatum://dataset/{path}/schema`, `undatum://dataset/{path}/sample`, `undatum://formats`.
- Prompts: `profile-dataset`, `draft-validation-rules`, `plan-conversion`, `document-dataset`,
  each parameterized by a dataset path.
- Resources honour the sandbox from `update-security-hardening` and bounded sample sizes.

## Impact
- Affected specs: `agent-integration`
- Affected code: `undatum/mcp/server.py`, `undatum/tools/`, `docs/docs/integrations/mcp.md`
- Depends on: `update-security-hardening`, `refactor-sdk-and-agent-adapters`
