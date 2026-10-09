## 1. Fix
- [x] 1.1 Make `starlette`, `fastapi`, `uvicorn` imports in `undatum/cmds/api.py` lazy
- [x] 1.2 Scan modules imported by `undatum.core` (pkgutil walk in a no-extras venv) and make all
      extra-only imports lazy
- [x] 1.3 Route missing-extra failures to `DependencyError` with the extra name and install hint

## 2. Tests
- [x] 2.1 Add `tests/test_base_install_imports.py` that walks `undatum.core` imports with extras
      hidden (import blocker fixture) and asserts no `ModuleNotFoundError`
- [x] 2.2 Add a CLI test: `undatum api serve` without the `api` extra exits 2 with the install hint
- [ ] 2.3 Run the existing `install-gate` job against the fix (see `update-ci-enforcement`)

## 3. Release
- [ ] 3.1 Release v1.7.1 with a CHANGELOG entry describing the broken 1.7.0 install
- [ ] 3.2 Decide on yanking 1.7.0 on PyPI and record the decision in the release notes
