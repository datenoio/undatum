## MODIFIED Requirements

### Requirement: Optional AI augmentation
When `--autodoc` is enabled and an AI provider is configured, the system SHALL
enrich dataset summaries, field descriptions, and structured metadata through the same AI
integration used by `undatum ai doc`; if AI initialization fails, it SHALL continue without AI
enhancements.

#### Scenario: AI provider unavailable
- **WHEN** `--autodoc` is enabled but the provider cannot initialize
- **THEN** the documentation is still generated without AI content

#### Scenario: Structured metadata generated
- **WHEN** `--autodoc` is enabled and the provider returns structured metadata
- **THEN** the documentation includes AI-enriched metadata values

#### Scenario: Legacy provider configuration still works
- **WHEN** `UNDATUM_AI_PROVIDER=openrouter` is set and user runs `undatum doc data.csv --autodoc`
- **THEN** the request goes to OpenRouter through the shared AI integration

## ADDED Requirements

### Requirement: Sample Masking Default for Remote Providers
When AI augmentation sends sample records to a remote provider, the system SHALL mask detected
PII in those samples by default and SHALL allow opting out with `--no-pii-mask-samples`.

#### Scenario: Remote provider receives masked samples
- **WHEN** user runs `undatum doc customers.csv --autodoc` with a remote provider
- **THEN** sample values in detected PII fields (e-mail, phone) are redacted in the prompt

#### Scenario: Local provider
- **WHEN** the provider is Ollama or LM Studio on localhost
- **THEN** samples are sent unmasked unless `--pii-mask-samples` is given
