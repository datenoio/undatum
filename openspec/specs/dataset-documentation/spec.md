# dataset-documentation Specification

## Purpose
Generate human-readable dataset documentation (`doc` / `ai doc`) with optional LLM-backed descriptions and metadata.
## Requirements
### Requirement: Document command availability
The system SHALL provide a CLI command `doc` with alias `document` to generate
dataset documentation for a provided input file.

#### Scenario: Generate documentation for a dataset
- **WHEN** the user runs `undatum doc <input-file>`
- **THEN** the system outputs a documentation report for that dataset

#### Scenario: Alias uses the same behavior
- **WHEN** the user runs `undatum document <input-file>`
- **THEN** the system behaves identically to `undatum doc`

### Requirement: Output formats
The system SHALL support documentation output in `markdown` (default), `json`,
`yaml`, and `text` formats.

#### Scenario: Generate JSON output
- **WHEN** the user runs `undatum doc <input-file> --format json`
- **THEN** the system outputs structured JSON documentation

### Requirement: Documentation contents
The documentation MUST include dataset metadata, schema field listings,
statistics summaries, and sample records when available.

#### Scenario: Core sections are present
- **WHEN** the system generates a documentation report
- **THEN** the output includes metadata, schema, statistics, and samples sections

### Requirement: Output destination
The system SHALL write documentation to stdout by default and to a file path
when `--output` is provided.

#### Scenario: Write to a file
- **WHEN** the user provides `--output docs/dataset.md`
- **THEN** the system writes the documentation to that file

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

### Requirement: Streaming-safe processing
The documentation command MUST avoid loading entire datasets into memory and
MUST limit sample output to a configurable size.

#### Scenario: Large dataset sampling
- **WHEN** the input dataset is large
- **THEN** the system produces documentation using streaming analysis and
  includes only a bounded sample of records

### Requirement: Extended metadata fields
The documentation report SHALL include extended metadata fields for title, keywords,
geographic coverage, temporal coverage, languages, and EU data theme.

#### Scenario: Metadata includes extended fields
- **WHEN** the system generates a documentation report
- **THEN** the metadata contains `title`, `keywords`, `geographic_coverage`,
  `temporal_coverage`, `languages`, and `data_theme` keys (empty or null if unknown)

### Requirement: EU data theme classification
The system SHALL classify datasets using the EU Data Theme controlled vocabulary
and include the label and URI in the documentation metadata when classification is available.

#### Scenario: Data theme is provided
- **WHEN** the system can classify the dataset theme
- **THEN** the documentation includes a `data_theme` object with a vocabulary label and URI

#### Scenario: Data theme is unavailable
- **WHEN** the system cannot confidently classify the dataset theme
- **THEN** the `data_theme` metadata value is empty or null

### Requirement: Optional semantic typing
When semantic typing is enabled, the system SHALL include semantic type annotations
for schema fields in the documentation output.

#### Scenario: Semantic types enabled
- **WHEN** the user runs `undatum doc <input-file> --semantic-types`
- **THEN** the documentation includes per-field `semantic_types` annotations

### Requirement: Optional PII detection
When PII detection is enabled, the system SHALL identify PII fields and include a PII
summary in the documentation output.

#### Scenario: PII detection enabled
- **WHEN** the user runs `undatum doc <input-file> --pii-detect`
- **THEN** the documentation includes a `pii_fields` summary with matched types

### Requirement: Optional PII masking for samples
When PII masking is enabled, the system SHALL redact sensitive values in sample records.

#### Scenario: PII masking enabled
- **WHEN** the user runs `undatum doc <input-file> --pii-detect --pii-mask-samples`
- **THEN** the sample records are redacted for detected PII fields

### Requirement: Markdown metadata rendering
When documentation is emitted in `markdown` format, the system SHALL render
metadata attributes as readable key-value content rather than raw serialized
structures. Scalar values SHALL be rendered inline, list values SHALL be
rendered as comma-separated items, and object values SHALL be rendered as a
nested markdown list of key-value pairs. Empty or unknown values SHALL be
rendered as `-`.

#### Scenario: Metadata values are formatted consistently
- **WHEN** the system generates markdown documentation with metadata values
  containing scalars, lists, and objects
- **THEN** the metadata section renders readable values with lists and objects
  formatted as markdown content and empty values shown as `-`

### Requirement: Sample Masking Default for Remote Providers
When AI augmentation sends sample records to a remote provider, the system SHALL mask detected
PII in those samples by default and SHALL allow opting out with `--no-pii-mask-samples`.

#### Scenario: Remote provider receives masked samples
- **WHEN** user runs `undatum doc customers.csv --autodoc` with a remote provider
- **THEN** sample values in detected PII fields (e-mail, phone) are redacted in the prompt

#### Scenario: Local provider
- **WHEN** the provider is Ollama or LM Studio on localhost
- **THEN** samples are sent unmasked unless `--pii-mask-samples` is given

