## 1. Scope and approval

- [x] 1.1 Read preserving/DuckDB repack, the prior SQLite research and relevant specs.
- [x] 1.2 Record the user's implementation authorization and the offline-only design.
- [x] 1.3 Probe read-only VACUUM INTO, raw TEXT values, WITHOUT ROWID and WAL header behavior.
- [x] 1.4 Validate this change with OpenSpec strict mode before implementation.

## 2. Implementation

- [x] 2.1 Add typed SQLite manifest/table/proof models, offline/version/options preflight
  and native signature/output validation.
- [x] 2.2 Add native VACUUM INTO, persistent journal-mode retention, independent
  catalog/settings/rowid/storage-class/value verification and candidate digest proof.
- [x] 2.3 Integrate sqlite_offline, database guards, owned-sidecar cleanup, cumulative
  budgets and existing worker/dry-run/savings/results publication.

## 3. Validation and documentation

- [x] 3.1 Add meaningful preservation, unsupported-profile, sidecar, fault/resource and
  CLI regression tests, including WAL-mode and WITHOUT ROWID databases.
- [x] 3.2 Update CLI/capabilities, generated command reference, examples and changelog.
- [x] 3.3 Run relevant regression suites, docs/examples, Ruff and Python 3.10 mypy;
  record runtime compatibility, measured savings and remaining profile limits.
- [x] 3.4 Complete the checklist and rerun strict OpenSpec validation.
