## ADDED Requirements

### Requirement: Temporary File Lifecycle
The SDK SHALL delete every temporary file it creates for chained operations once the file is no
longer needed, and no later than when the `Dataset` is closed or the interpreter exits.

#### Scenario: Chain leaves no files behind
- **WHEN** user runs `Dataset.read("data.csv").fill("a", value=0).dedup().write("out.jsonl")`
- **THEN** no temporary files created by the chain remain after `write` returns

#### Scenario: Context manager
- **WHEN** user uses `with Dataset.read("data.csv") as ds:` and exits the block
- **THEN** all temporary files of `ds` are removed
