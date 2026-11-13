# Change: Support Only Maintained Python Versions (3.10+)

## Why
`pyproject.toml` declares `requires-python = ">=3.9"` and CI defines a 3.9 job, but four modules
use `X | None` annotations at runtime without `from __future__ import annotations`
(`common/command_utils.py` 36, `cmds/converter.py` 12, `cmds/schemer.py` 2, `cmds/selector.py` 1),
so the package cannot be imported on 3.9. Python 3.9 reached end of life in October 2025. Keeping
it costs compatibility shims and holds back dependency floors.

## What Changes
- **BREAKING**: `requires-python = ">=3.10"`; classifiers list 3.10–3.13 (3.14 once dependencies
  publish wheels).
- CI matrix, ruff/black `target-version` and mypy `python_version` move to 3.10.
- README, AGENTS.md, `openspec/project.md` and the installation page state the supported range.
- Policy: drop a Python version in the first minor release after its end of life.
- Alternative if this proposal is rejected: add `from __future__ import annotations` to the four
  modules, keep the 3.9 job blocking, and add a ruff rule (`FA102`) to prevent regressions.

## Impact
- Affected specs: `distribution`
- Affected code: `pyproject.toml`, `.github/workflows/*.yml`, docs
- Users on 3.9: pip resolves to the last 3.9-compatible release (1.6.0)
