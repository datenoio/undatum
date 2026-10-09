# Change: Remove the Legacy AI Provider Stack

## Why
undatum has two AI stacks. The `ai` command group uses iterabledata's `iterable.ai` (OpenAI,
Anthropic, Gemini, Azure, OpenRouter, Ollama, LM Studio, Perplexity). `--autodoc` on `analyze`,
`schema`, `doc` and `package` uses the in-house `undatum/ai/providers.py` (1 369 lines, 6% test
coverage) plus `undatum/ai/perplexity.py`. The OpenAI, OpenRouter and Perplexity provider classes
are ~96% identical, default models are hard-coded (`gpt-4o-mini`), and the legacy path does not
offer the PII masking that `ai doc --pii-mask-samples` provides. `ai/providers.py` alone is the
largest block of untested code in the package (591 uncovered statements).

## What Changes
- `--autodoc` runs on `iterable.ai` through the same code path as `ai doc`.
- Configuration compatibility: `UNDATUM_AI_PROVIDER`, `--ai-provider`, `--ai-model`,
  `--ai-base-url`, config-file keys and provider names keep working (mapped to iterable.ai).
- Remote providers mask detected PII in sample rows by default; `--no-pii-mask-samples` opts out.
- Delete `undatum/ai/providers.py`, `undatum/ai/perplexity.py` and unused parts of
  `undatum/ai/base.py`; keep `undatum/ai/config.py` and `doc_enrichment.py` as thin adapters.

## Impact
- Affected specs: `dataset-documentation`
- Affected code: `undatum/ai/`, `undatum/cmds/analyzer.py`, `schemer.py`, `doc.py`, `packager.py`,
  `undatum/common/parallel.py`, tests in `tests/test_ai_*.py`
- Expected coverage effect: total line coverage rises from 65% to ~67% without new tests
