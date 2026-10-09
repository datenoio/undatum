## ADDED Requirements

### Requirement: Per-Resource Pagination Limits
Each Data API resource SHALL enforce its own configured `default_limit` and `max_limit`
independently of other resources in the same configuration.

#### Scenario: Two resources with different limits
- **WHEN** resource `a` has `max_limit: 10` and resource `b` has `max_limit: 1000`
- **AND** a client requests `/a?limit=50`
- **THEN** the server rejects the request for exceeding 10
- **AND** a request to `/b?limit=50` succeeds
