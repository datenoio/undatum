# Change: Homebrew, Container Image and conda-forge Distribution

## Why
Installation today means pip/pipx/uv; the v1.7.0 release has no binaries, macOS users have no
Homebrew formula, there is no container image for CI and data platforms, and there is no
conda-forge package for the scientific Python audience. Combined with the broken 1.7.0 wheel, new
users have no reliable path.

## What Changes
- Homebrew formula in a `datenoio/homebrew-tap` (and a homebrew-core submission once stable),
  updated automatically on release.
- Container image `ghcr.io/datenoio/undatum:<version>` (slim base, non-root user, `undatum` as
  entrypoint), plus a `-full` variant with all extras; built and smoke-tested on release.
- conda-forge feedstock with the core dependencies.
- README and installation page list all channels with the same smoke command.

## Impact
- Affected specs: `distribution`
- Affected code: `packaging/` (Dockerfile, formula template), `.github/workflows/release.yml`,
  README, `docs/docs/getting-started/installation.md`
- Depends on: `update-release-pipeline`, `fix-base-install-optional-imports`
