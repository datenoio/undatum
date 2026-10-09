## 1. Pipeline
- [x] 1.1 Restructure `release.yml`: test → install-gate → build → binaries → publish (needs all)
- [ ] 1.2 Add a protected `pypi` environment approval before publish
- [x] 1.3 Attach wheels, sdist and binaries to the GitHub release in the final job
- [x] 1.4 RC tags publish to TestPyPI and install-smoke from TestPyPI

## 2. Versioning and changelog
- [x] 2.1 Single-source the version; remove the literal from `undatum/__init__.py`
- [x] 2.2 Adopt release-please (or git-cliff) and seed it from the current CHANGELOG

## 3. Supply chain
- [x] 3.1 Add `uv.lock`; use it in CI and PyInstaller builds
- [x] 3.2 Add `pip-audit` job (fail on known vulnerabilities with documented ignores)
- [x] 3.3 Add `actions/attest-build-provenance` for distributions and binaries

## 4. Binaries
- [x] 4.1 Trigger binary builds on PRs touching `packaging/**` or `release.yml`
- [ ] 4.2 Publish binaries for v1.7.1 and update README links
