## 1. Decision
- [x] 1.1 Approve 3.10+ or choose the alternative (future annotations + blocking 3.9 job)

## 2. Implementation (3.10+)
- [x] 2.1 Update `requires-python`, classifiers, ruff/black/mypy targets
- [x] 2.2 Update CI matrices in `ci.yml` and `install-gate`
- [x] 2.3 Run `ruff --select UP --target-version py310 --fix` for safe modernizations
- [x] 2.4 Update README, AGENTS.md, `openspec/project.md`, installation docs, CHANGELOG (BREAKING)

## 3. Policy
- [x] 3.1 Document the end-of-life policy in CONTRIBUTING.md
