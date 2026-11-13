## 1. Channels
- [ ] 1.1 Homebrew tap with formula; release job bumps it (`datenoio/homebrew-tap` holds the
      2.0.1 formula and tests it on macOS; the release job needs the `HOMEBREW_TAP_TOKEN` secret)
- [x] 1.2 Dockerfile (slim and full), GHCR publishing, smoke test in release
- [ ] 1.3 conda-forge feedstock and maintainer setup (recipe in `packaging/conda/meta.yaml`;
      blocked until iterabledata and qddate have conda-forge feedstocks)

## 2. Docs
- [x] 2.1 Installation page and README updated with all channels
