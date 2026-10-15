# SQLite repack validation

Implemented on 2026-10-15 following the user's request to implement the SQLite path
from the preceding research.

## Result

SQLite header detection selects native VACUUM INTO. An offline source is read-only;
independent catalog/settings/typed-value/rowid verification binds the finalized
candidate digest before existing atomic publication. The existing metadata, savings,
dry-run, JSON result and worker policies are reused. Closed WAL mode is restored on
the candidate and verified. Shared parent/worker scratch accounting includes owned
sidecars, which the parent also removes after worker failure.

An existing destination requires `--sqlite-offline` / `sqlite_offline=True`; a new
distinct output and dry-run do not require the replacement assertion. Source/output
WAL, SHM and journal sidecars remain prohibited and are never deleted.

## Checks

| Check | Result |
|---|---|
| SQLite suite, Python 3.13.7 / SQLite 3.53.3 | 80 passed |
| SQLite suite, Python 3.10.20 / SQLite 3.50.4 | 80 passed |
| Combined SQLite/DuckDB/repack/preservation/resources/CLI conventions/docs suite | 231 passed, 4 optional-codec skips |
| Python 3.10 mypy ratchet, complete locked dev environment | 454 errors, baseline 454; no new errors |
| Ruff lint and format on touched Python files | Passed |
| Generated command documentation | Regenerated; freshness tests passed |
| Executable repack documentation examples | 9/9 passed |
| Dependency bound validation | Passed; no new dependency or version increase |
| OpenSpec strict validation | Passed |

The combined suite reports existing qddate/Pyparsing deprecations. The four skips are
existing optional-codec cases, not SQLite tests. SQLite 3.31 is the feature minimum;
the available native runtimes tested here are 3.50.4 and 3.53.3.

Tests cover sparse/negative rowids, INTEGER PRIMARY KEY DESC, shadowed aliases,
composite/NOCASE WITHOUT ROWID keys, NULL/integer/real/inf/raw TEXT/BLOB values,
invalid UTF-8, UTF-16, quoted names/paths, a 4 MiB BLOB, empty databases/tables,
foreign keys/checks/indexes/views/triggers, generated values, AUTOINCREMENT/statistics,
closed WAL mode, actual in-place replacement, dry-run/no-benefit/savings fallback,
budgets, worker/native failures, progress interruption and newly appearing sidecars.
Changed values, storage classes, rowids/counts, indexes, user versions and sequence
counters are refused. Physical profiles with reserved bytes or trailers fail preflight.

## Measured fragmented fixture

[benchmark.json](benchmark.json) records a real run of
`tests/test_repack_sqlite.py::database(fragmented=True, journal="WAL")`.

| Item | Bytes |
|---|---:|
| Original database | 5,570,560 |
| Compact candidate | 122,880 |
| Observed candidate plus sidecar scratch peak | 155,648 |

Savings were **97.7941%** on this deliberately fragmented fixture. Original bytes were
unchanged, and source/candidate both retained WAL header values `[2, 2]`. The report
includes 35 stored records (including sequence/statistics), 1,476 source verification
bytes and 4,428 cumulative bytes across source plus both verification scans. This is
one mechanism/preservation fixture, not a general size or throughput guarantee.

## Limits

- Offline files and SQLite >=3.31; live backup/WAL snapshots and compression-VFS
  formats remain separate work. No fallback to ordinary VACUUM.
- No added total file/row cap. Catalog/table metadata is limited to 4 MiB and tables
  to 999 columns. Batches are capped at 1024 rows; single values and native allocations
  may exceed a transfer batch's size. Hard RSS/time limits use the existing worker.
- Virtual tables, unavailable collations/table-expression functions and inaccessible
  hidden rowids are refused. WITHOUT ROWID keys use primary-index metadata.
- Extension-reserved bytes, opaque trailers and incomplete physical pages are refused
  before staging because native compaction cannot prove their retention.
- The offline assertion and missing sidecars do not establish exclusive ownership
  against a database user opening a file during replacement. Existing atomic-visibility
  and durability limits remain unchanged.
- Results report codec none, null level, vacuum_into strategy and SQLite runtime;
  shared profiles select the same compaction operation.
