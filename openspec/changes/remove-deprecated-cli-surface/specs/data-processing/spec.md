## REMOVED Requirements

### Requirement: Scheme Command Deprecation
**Reason**: The deprecation period ends with v2.0; `schema --format cerberus` fully replaces
`scheme`.
**Migration**: Replace `undatum scheme data.jsonl` with `undatum schema data.jsonl --format cerberus`.
