## MODIFIED Requirements

### Requirement: Official macOS Install Path
The project SHALL ship a Homebrew formula that installs undatum on macOS and is updated for every
release, and SHALL document it as the official macOS installation path next to pipx and uv.

#### Scenario: macOS user finds supported install
- **WHEN** a macOS user follows project docs to install undatum
- **THEN** they have a documented supported path (Homebrew formula and/or pipx/uv) without
  relying on an abandoned help-wanted issue alone

#### Scenario: Homebrew install
- **WHEN** a macOS user runs `brew install datenoio/tap/undatum`
- **THEN** `undatum --version` prints the latest released version

## ADDED Requirements

### Requirement: Container Image
Each release SHALL publish a container image with undatum as the entrypoint, running as a non-root
user, and verified by a smoke test before publication.

#### Scenario: Run in a container
- **WHEN** a user runs `docker run --rm -v "$PWD:/data" ghcr.io/datenoio/undatum:latest stats /data/file.csv`
- **THEN** statistics for `file.csv` are printed

### Requirement: Conda-Forge Package
The project SHALL maintain a conda-forge package for undatum releases.

#### Scenario: Conda install
- **WHEN** a user runs `conda install -c conda-forge undatum`
- **THEN** the latest released version is installed and `undatum --version` succeeds
