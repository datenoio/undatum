## 1. Channels
- [ ] 1.1 Homebrew tap with formula; release job bumps it (formula template, render script and
      release job ready in `packaging/homebrew/` and `release.yml`; needs the `datenoio/homebrew-tap`
      repository, the `HOMEBREW_TAP_REPO` variable and the `HOMEBREW_TAP_TOKEN` secret)
- [x] 1.2 Dockerfile (slim and full), GHCR publishing, smoke test in release
- [ ] 1.3 conda-forge feedstock and maintainer setup (recipe in `packaging/conda/meta.yaml`;
      blocked until iterabledata and qddate have conda-forge feedstocks)

## 2. Docs
- [x] 2.1 Installation page and README updated with all channels
