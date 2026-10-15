# Change: Add preserving SQLite database compaction

## Why

The preceding DuckDB change researched SQLite's `VACUUM INTO` as the next native
repack adapter. The user now explicitly requests implementation of that researched
offline compaction path. SQLite needs preservation checks for row identities, storage
classes and application metadata as well as the existing atomic publication policy.

## What Changes

- Detect SQLite by its native header, including `.db` and extensionless files, and
  compact a read-only offline source into a sibling candidate using `VACUUM INTO`.
- Verify ordinary tables (including `WITHOUT ROWID`), storage classes and raw values,
  implicit rowids, schema/index/trigger/view definitions, sequence/statistics tables,
  encoding, application/user versions, page size, auto-vacuum and persistent WAL mode.
- Reuse atomic publication, source/destination guards, measured dry-run, savings policy,
  `undatum.repack/1` and resource supervision. Account for and clean owned SQLite sidecars.
- Add `--sqlite-offline` / `sqlite_offline=True` to assert closed database users before
  replacing an existing path. A new distinct output and dry-run do not require it.
- Refuse source/destination WAL/SHM/journal sidecars even when offline is asserted;
  live/WAL snapshots remain a separate capability. Never fall back to plain `VACUUM`.
- Accept omitted, `auto` or `none` compression; report `codec=none`, `level=null` and
  `strategy=vacuum_into`. All profiles use the same compaction operation, with one thread.
- Use Python's sqlite3 and SQLite >=3.31 (VACUUM INTO, table_xinfo and trusted_schema).
  Stream values without total file/row limits; initially cap catalog metadata at 4 MiB
  and tables at 999 columns to keep paired type/value verification queries portable.
- Refuse virtual tables, unavailable table-expression collations/functions and inaccessible implicit
  rowids rather than silently skipping content. Native format/compression conflicts fail
  before allocating a candidate.
- Refuse extension-reserved page bytes and trailing/incomplete physical pages whose
  opaque contents cannot be retained by native compaction.

## Impact

- Affected specs: additive `data-repacking` requirements alongside the implemented,
  unarchived preserving core and DuckDB changes. Pending Arrow/effort changes are separate.
- Affected code: SQLite adapter, repack detection/dispatch/options/sidecar hooks,
  supervised budgets, CLI help/capabilities, tests, command documentation and changelog.
- No new package dependency or incompatible result-schema change.
- Status: implemented and verified; see [validation.md](validation.md) for checks
  and measured fixture evidence.
- Authorization: the user's 2026-10-15 instruction "Реализуй для SQlite" follows the
  concrete SQLite design in `add-duckdb-repack/research.md` and authorizes implementing
  that offline path. The proposal records that scope before implementation; no repeated
  confirmation is required for the already requested capability.
