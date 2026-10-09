## 1. Triggers and protection
- [x] 1.1 Change `ci.yml` triggers to `branches: [master, main]` for push and pull_request
- [ ] 1.2 Enable branch protection on `master` with required checks (lint, test, install-gate,
      base-install, docs)
- [ ] 1.3 Confirm Dependabot PRs now get CI runs

## 2. Clean baseline
- [x] 2.1 Fix the 18 ruff findings (B023 handled in `fix-runtime-defects`)
- [x] 2.2 Reformat the 12 drifting files with the pinned formatter version
- [x] 2.3 Set `--cov-fail-under=65` and document the ratchet schedule (70 → 75 → 80)
- [x] 2.4 Add diff-coverage (e.g. `diff-cover`) at 80% for PRs

## 3. New jobs
- [x] 3.1 Base-install job: wheel without extras, import walk, `undatum --version`, smoke commands
- [x] 3.2 Contract suite job: `tests/test_output_contract.py` and CLI golden tests
- [x] 3.3 DB integration job with service containers; un-skip ingester tests there
- [x] 3.4 Lowest-direct dependency job on the oldest supported Python
- [x] 3.5 Deprecation job: `-W error::DeprecationWarning:undatum`

## 4. Test hygiene
- [x] 4.1 Remove `tests/test.py` from collection (move to `scripts/` or delete)
- [x] 4.2 Consolidate duplicated fixtures into `tests/conftest.py`
      (`sample_csv_file` / `sample_jsonl_file` read per-module `SAMPLE_CSV` / `SAMPLE_JSONL`;
      `semicolon_csv` shared; 17 copies removed)
- [x] 4.3 Replace `assert True` placeholders with real assertions
