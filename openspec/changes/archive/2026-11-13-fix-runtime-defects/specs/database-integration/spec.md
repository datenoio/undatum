## ADDED Requirements

### Requirement: Elasticsearch Client Compatibility
The Elasticsearch loader SHALL construct its client with arguments supported by the declared
elasticsearch-py major versions and SHALL pass the timeout as a request timeout.

#### Scenario: Load with elasticsearch-py 9
- **WHEN** elasticsearch-py 9.x is installed and user runs an Elasticsearch load with a timeout
- **THEN** the client is created without a `TypeError` and requests use that timeout
