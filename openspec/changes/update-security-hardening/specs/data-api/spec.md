## MODIFIED Requirements

### Requirement: API Key Authentication
The system SHALL support optional API-key authentication for `api serve` and `api run` when
configured via `--api-key` or the `UNDATUM_API_KEY` environment variable. The key SHALL be
accepted only in the `X-API-Key` header, compared in constant time, and never written to logs.

#### Scenario: Reject unauthenticated request
- **WHEN** the server is started with an API key configured
- **AND** a client omits the key
- **THEN** the server responds with HTTP 401

#### Scenario: Key in query string ignored
- **WHEN** a client sends the correct key only as `?api_key=...`
- **THEN** the server responds with HTTP 401
- **AND** the access log line does not contain the key

## ADDED Requirements

### Requirement: Non-Blocking Query Execution
The Data API SHALL execute DuckDB queries outside the event loop with a configurable per-request
timeout so that one slow request does not block other clients.

#### Scenario: Concurrent requests
- **WHEN** one client runs a slow filtered query and another requests a small page
- **THEN** the small page is served without waiting for the slow query

#### Scenario: Query timeout
- **WHEN** a query exceeds the configured timeout
- **THEN** the server responds with HTTP 504 and cancels the query
