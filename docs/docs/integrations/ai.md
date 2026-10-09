---
title: "AI documentation"
description: "Block-based docs, providers, and configuration"
---
# AI-powered documentation

undatum offers several AI documentation paths:

| Command | Best for |
|---------|----------|
| `ai doc` | Block-based docs (general, schema, quality, …) with schema enrichment — **recommended** |
| `doc --autodoc` | Markdown/JSON/YAML dataset documentation with metadata and PII options |
| `analyze --autodoc` | Human-readable analysis report with field descriptions |
| `schema --autodoc` / `schema-bulk --autodoc` | Schema files with AI field descriptions |
| `package create --autodoc` | Frictionless Data Package metadata |

All of them use iterabledata's providers: `openai`, `anthropic`, `gemini`, `azure`,
`openrouter`, `ollama`, `lmstudio`, `perplexity` and `openai-compatible`. Pick one with
`--ai-provider` (or `--provider` for `ai *`), `UNDATUM_AI_PROVIDER`, or the `ai:` section of
`undatum.yaml`. Without any of these, the first API key found in the environment decides
(`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `PERPLEXITY_API_KEY`, `ANTHROPIC_API_KEY`,
`GEMINI_API_KEY`).

### What is sent, and PII masking

Field descriptions send field names only. Dataset descriptions (`analyze`) and structured
metadata (`doc`, `package create`) also send a short CSV sample of the data, at most 4,000
characters.

Before a sample goes to a **remote** provider, undatum masks values in columns that look like
personal data (names containing `email`, `phone`, `mobile`, `ssn`, ...): they are sent as `***`.
Samples for **local** providers (`ollama`, `lmstudio`) are sent as they are.

| Setting | Effect |
|---------|--------|
| `--no-pii-mask-samples` | Send samples unmasked, also to remote providers |
| `--pii-mask-samples` | Mask samples, also for local providers |
| `UNDATUM_AI_PII_MASK_SAMPLES=false` / `true` | The same, from the environment |
| `pii_mask_samples: false` under `ai:` in `undatum.yaml` | The same, from the config file |

Masking works on column names. It does not find personal data in free-text columns, so review
what a dataset contains before sending samples of it to a remote service.

### Quick Examples

```bash
# Recommended: block-based documentation
undatum ai doc data.csv --format-out json --blocks general,schema,quality

# Analysis report with field descriptions and a dataset summary
undatum analyze data.csv --autodoc --ai-provider anthropic

# Local model: samples are not masked unless you ask for it
undatum analyze data.csv --autodoc --ai-provider ollama --ai-model llama3.2

# Dataset documentation with PII detection
undatum doc data.csv --autodoc --pii-detect --format-out markdown

# Schema with AI field descriptions
undatum schema data.csv --autodoc --format jsonschema --output schema.json
```

### Configuration File Example

Create `undatum.yaml` in your project:

```yaml
ai:
  provider: openai
  model: gpt-4o-mini
  timeout: 30
```

Or use `~/.undatum/config.yaml` for global settings:

```yaml
ai:
  provider: ollama
  model: llama3.2
  ollama_base_url: http://localhost:11434
```

`./undatum.yaml` is preferred over `~/.undatum/config.yaml`. CLI `--ai-provider` / `--ai-model` flags override the file. Provider API keys stay in the environment (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `AZURE_OPENAI_API_KEY` with `AZURE_OPENAI_ENDPOINT`, `OPENROUTER_API_KEY`, `PERPLEXITY_API_KEY`). Full `defaults:` keys: [`config`](/commands/config).

### Language Support

Generate descriptions in different languages:

```bash
# English (default)
undatum analyze data.csv --autodoc --lang English

# Russian
undatum analyze data.csv --autodoc --lang Russian

# Spanish
undatum analyze data.csv --autodoc --lang Spanish
```

### What Gets Generated

With `--autodoc` enabled, the analyzer will:

1. **Field Descriptions**: Generate clear, concise descriptions for each field explaining what it represents
2. **Dataset Summary**: Provide an overall description of the dataset based on sample data

Example output:

```yaml
tables:
  - id: data.csv
    fields:
      - name: customer_id
        ftype: VARCHAR
        description: "Unique identifier for each customer"
      - name: purchase_date
        ftype: DATE
        description: "Date when the purchase was made"
    description: "Customer purchase records containing transaction details"
```

Provider connection issues: [troubleshooting](/getting-started/troubleshooting#ai-provider-troubleshooting).
Command reference: [`ai`](/commands/ai), [`doc`](/commands/doc).
