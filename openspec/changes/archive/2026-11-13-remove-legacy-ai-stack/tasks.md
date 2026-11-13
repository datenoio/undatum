## 1. Migration
- [x] 1.1 Route `--autodoc` in analyze/schema/doc/package through the `ai doc` implementation
      (`undatum/ai/service.py`: an `AIService` dataclass over `iterable.ai` providers; each command
      keeps its own output shape)
- [x] 1.2 Map legacy provider names, env vars and config keys to iterable.ai settings
- [x] 1.3 Default PII masking for remote providers; `--no-pii-mask-samples` opt-out; local
      providers (Ollama, LM Studio) unchanged

## 2. Removal
- [x] 2.1 Delete `undatum/ai/providers.py`, `undatum/ai/perplexity.py`, dead parts of `base.py`
- [x] 2.2 Remove or rewrite tests that targeted the legacy classes

## 3. Verification
- [x] 3.1 Tests with a fake iterable.ai provider for each `--autodoc` command
- [x] 3.2 CHANGELOG: note masking default and removed internal classes
