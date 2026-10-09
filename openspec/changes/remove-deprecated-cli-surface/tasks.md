## 1. Removal
- [ ] 1.1 Remove `scheme` command and its tests (at the 2.0 release; aliases must ship deprecated
      for at least two minor releases first)
- [ ] 1.2 Remove hidden command aliases and option aliases
- [ ] 1.3 Decide on `--autodoc` based on issue/discussion signals

## 2. Migration support
- [x] 2.1 Migration guide page with rewrite table (`docs/docs/getting-started/migrating-to-2.md`,
      checked against the live alias tables by `tests/test_migrate_script.py`)
- [x] 2.2 `undatum migrate-script` for shell scripts and pipeline YAML
- [x] 2.4 Pipelines can use `db load` (`command: db load`), so removing `ingest` leaves no gap
- [ ] 2.3 CHANGELOG and release notes list every removal (BREAKING)
