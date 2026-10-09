## 1. Toolchain
- [x] 1.1 Switch to `ruff format`; reformat once; remove black from dev deps, pre-commit and CI
- [x] 1.2 Enable selected `PL` and `D` rules (scoped); remove pylint
- [x] 1.3 Pin tool versions in one place (dependency group) and reference them from pre-commit/CI
- [x] 1.4 mypy: per-module overrides, strict for `common/` and `sdk/`, CI blocking with a
      baseline file that may only shrink

## 2. Legacy configuration
- [x] 2.1 Delete `tox.ini`, `setup.cfg`, `flake8`, `requirements.txt`; move `.coveragerc` into
      `pyproject.toml`
- [x] 2.2 Update Makefile targets and CONTRIBUTING.md

## 3. Dependencies
- [x] 3.1 Add `elastic` and `all` extras (pymongo stays: it provides `bson`); lazy imports and
      DependencyError hints
- [x] 3.2 Add bounds to every direct dependency
- [x] 3.3 Replace `tqdm` and `tabulate` usages with `rich`; replace `chardet` with iterabledata
      detection
- [x] 3.4 Replace or retire `xlwt`
- [x] 3.5 Record the base-install size and package count in CI output

## 4. Governance
- [x] 4.1 Add `SECURITY.md`, `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md`,
      `.github/CODEOWNERS`
- [ ] 4.2 Delete the 17 `snyk-fix-*` branches and merged `codex/*` branches
- [ ] 4.3 Enable Dependabot auto-merge for patch updates with green CI (workflow added; needs
      "Allow auto-merge" and required checks in the repository settings)
