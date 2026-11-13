# Change: Make CI Run on master and Enforce Its Checks

## Why
`.github/workflows/ci.yml` triggers on `push`/`pull_request` to `main`, but the default branch is
`master`; `gh run list --workflow ci.yml` returns no runs at all. As a result `master` carries
18 ruff errors, 12 black diffs, a Python 3.9 import failure and the broken 1.7.0 install, even
though lint, a 3.9–3.13 matrix and a clean-wheel `install-gate` job are all defined. Coverage is
65% (17 266 statements, 6 090 missed) with a 50% threshold that never runs; only 13 of 78 test
files exercise the CLI; PostgreSQL/MySQL ingesters sit at 10% coverage; the suite emits 4 200
deprecation warnings.

## What Changes
- Trigger CI on `master` (and `main` for forward compatibility) and on all pull requests.
- Protect `master`: lint, test matrix, `install-gate`, base-install import test and docs build are
  required checks.
- Add a base-install job (no extras) that imports every module reachable from `undatum.core`.
- Bring ruff and the formatter to zero findings in one PR, then keep them blocking.
- Coverage ratchet: fail-under 65 now, raised to 70/75/80 by milestone; diff coverage ≥ 80% on PRs.
- Add the command × output-format contract suite and CliRunner golden tests that assert exit
  codes.
- Add a database integration job with PostgreSQL, MySQL, MongoDB and Elasticsearch service
  containers.
- Add a lowest-direct dependency job (`uv pip install --resolution lowest-direct`).
- Add a job that turns `DeprecationWarning` raised from `undatum` code into errors.
- Housekeeping: move `tests/test.py` (debug script) out of the suite; move duplicated
  `sample_csv_file` fixtures into `tests/conftest.py`.

## Impact
- Affected specs: `release-quality`
- Affected code: `.github/workflows/ci.yml`, `tests/`, repository branch-protection settings
