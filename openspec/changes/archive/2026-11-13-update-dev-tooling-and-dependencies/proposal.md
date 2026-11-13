# Change: Simplify Dev Tooling and Slim the Dependency Footprint

## Why
- Four quality tools (black, ruff, pylint, mypy) run with different versions: pre-commit pins
  ruff 0.6.9 and black 24.8, the local venv has ruff 0.14.9 and black 25.1, CI installs the
  latest. The result is permanent formatting drift (12 files).
- mypy stops at the first file under the configured `python_version = 3.9` and reports 666 errors
  in 83 of 148 files under 3.13; type checking is advisory.
- Legacy configuration files remain: `tox.ini` (envlist `py38`, path `./datus` from an old project
  name), `setup.cfg` and a file named `flake8` (flake8 is not used), `requirements.txt` that
  diverges from `pyproject.toml` (`click`, `setuptools`).
- The base install is 70 packages / 332 MB (pyarrow 125, duckdb 44, pandas 41, numpy 22, lxml 21,
  pyorc 17 MB). `pymongo`, `elasticsearch` and `dnspython` are core dependencies although
  PostgreSQL and MySQL drivers are extras. Ten dependencies have no version constraint at all
  (`duckdb`, `pydantic`, `typer`, `elasticsearch`, `requests`, `pyyaml`, `pyzstd`, `tqdm`, `xlwt`,
  `xxhash`). Two libraries serve the same purpose in three places (`tqdm`+`rich` progress,
  `tabulate`+`rich` tables, `chardet`+iterabledata detection); `xlwt` is unmaintained.
- No `SECURITY.md`, issue/PR templates or `CODEOWNERS`; 17 stale `snyk-fix-*` branches on origin.

## What Changes
- Toolchain: `ruff format` replaces black; `ruff check` gains selected `PL` rules (replacing
  pylint) and `D` (Google docstrings) for `undatum/cmds/` and `undatum/sdk/`; pylint removed.
  One pinned version per tool shared by the `dev` dependency group, pre-commit and CI.
- Type checking: mypy configured for the supported minimum Python; per-module ratchet (start with
  `common/` and `sdk/` strict), CI blocking for ratcheted modules, error count may only decrease.
- Remove `tox.ini`, `setup.cfg`, `flake8`, `requirements.txt`; `.coveragerc` folded into
  `pyproject.toml`.
- **BREAKING (minor)**: move `pymongo`/`dnspython` to a `mongo` extra and `elasticsearch` to an
  `elastic` extra; `undatum[all]` meta-extra for the previous behaviour.
- Lower and upper bounds for every direct dependency; drop `tqdm`, `tabulate` and `chardet` in
  favour of `rich` and iterabledata detection; replace `xlwt` (`.xls` writing) with iterabledata's
  writer or document `.xls` as read-only.
- Governance: `SECURITY.md`, issue and PR templates, `CODEOWNERS`, delete stale `snyk-fix-*`
  branches, auto-merge passing Dependabot patch updates.

## Impact
- Affected specs: `release-quality`, `distribution`, `community`
- Affected code: `pyproject.toml`, `.pre-commit-config.yaml`, `Makefile`,
  `.github/workflows/ci.yml`, `.github/`, removed legacy files, modules using `tqdm`/`tabulate`/
  `chardet`/`xlwt`
