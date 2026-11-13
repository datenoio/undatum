---
title: "Releasing"
description: "How a version is cut, tested and published"
---
# Releasing

Releases are cut from `master` by pushing a tag. `.github/workflows/release.yml` publishes
nothing unless every earlier job succeeds.

## Steps

1. Make sure CI on `master` is green.
2. Set the version in `undatum/__init__.py` (`__version__`; the only place it is defined).
3. Move the `Unreleased` entries in `CHANGELOG.md` under the new version and date.
   `make changelog` (git-cliff, `cliff.toml`) previews the entries from Conventional Commits.
4. Commit (`chore: release X.Y.Z`), then tag and push:

```bash norun
git tag vX.Y.Z
git push origin master vX.Y.Z
```

Use a tag such as `vX.Y.Zrc1` for a release candidate: it goes to TestPyPI and is installed
from there as a check, without touching PyPI.

## What the workflow does

| Job | Purpose |
|-----|---------|
| verify | the tag matches `__version__`; `rc` tags are marked as pre-releases |
| test | full test suite on Python 3.11 and 3.13 |
| build | sdist and wheel with build provenance attestations |
| install-gate | the built wheel installs into a clean environment and real commands run |
| binaries | PyInstaller single-file binaries for Linux, macOS and Windows (attested) |
| publish-testpypi / verify-testpypi | release candidates only |
| publish-pypi | final releases; waits until a maintainer approves the deployment to the `pypi` environment |
| github-release | GitHub release with notes from the commits, the distributions and binaries |
| homebrew | renders `packaging/homebrew/undatum.rb.in`, installs and tests it on macOS and commits it to [datenoio/homebrew-tap](https://github.com/datenoio/homebrew-tap); runs when the `HOMEBREW_TAP_REPO` variable is set and needs the `HOMEBREW_TAP_TOKEN` secret (contents: write on the tap) |

## Versioning policy

- Semantic versioning for the CLI and the SDK.
- Breaking changes are listed under **Breaking** in the changelog. Renamed options and
  commands keep working with a deprecation warning for at least one minor release and are
  removed in the next major version (the current list is in
  [shared options](/commands/shared-options)).
- Core verbs (`convert`, `stats`, `validate`, `select`) keep their behaviour across minor
  releases.
