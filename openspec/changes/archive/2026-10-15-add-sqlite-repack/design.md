# SQLite compaction design

## Scope and preservation

Implement the offline path described in the preceding research. Use `VACUUM INTO`
against a read-only source, then independently reopen and verify source/candidate.
Do not rebuild records through RecordSink and do not substitute `backup + VACUUM`:
ordinary VACUUM can renumber implicit rowids.

Detect the full SQLite header. `.db` remains ambiguous between SQLite/DuckDB and is
resolved by magic. Keep compressed database inputs on the outer byte-stream path.
Native output cannot declare another format or an outer compression suffix.

SQLite tables have no general implicit row order. Compare rowid tables in hidden rowid
order, including sparse/negative rowids. Find an unshadowed `rowid`, `_rowid_` or `oid`
alias. Primary-index metadata identifies WITHOUT ROWID tables: an ordinary primary
index has an auxiliary cid=-1 rowid entry, while a WITHOUT ROWID primary index covers
actual columns. Verify WITHOUT ROWID tables in
canonical composite-primary-key order. Refuse all-shadowed aliases when row identities
cannot be accessed reliably. Never infer WITHOUT ROWID from a substring in a SQL literal.

Stream pairs of SQLite `typeof(column)` and values; return TEXT as BLOB bytes to avoid
Python text decoding/normalization and retain TEXT/BLOB distinctions, including invalid
UTF-8 and embedded NUL. Hash framed integers, IEEE floats, NULL and bytes with their
storage classes. Reopen both files for independent verification and bind the proof to
the finalized candidate SHA-256. Include internal sequence/statistics tables in checks.

Compare catalog definitions ordered by type/name and table_xinfo layouts, significant
PRAGMAs and native header journal mode. Require integrity_check success on both sides.
Use EXPLAIN-only queries to validate the verification projection and declared column
collations without executing views, triggers or user-supplied functions. Refuse virtual
tables. Preserve ordinary views/triggers as catalog definitions rather than selecting
from views or replaying inserts that could fire triggers.

## Connections and publication

Require SQLite >=3.31, disable extension loading when the runtime exposes that API,
and set trusted_schema=OFF. Source and verification connections use mode=ro plus
immutable=1 only under the offline/no-sidecar contract; this avoids creating WAL/SHM
files merely by reading a closed WAL-mode database. Do not use query_only=ON on the
source encoder: experimentation shows that it prevents VACUUM INTO as well.

VACUUM INTO changes a closed WAL database's persistent journal header to rollback mode.
Restore WAL mode on the owned candidate using a writable connection, checkpoint/close,
and verify the header before publication. No source-side checkpoint/recovery is performed.

The flag `--sqlite-offline` asserts closed database users before replacing any existing
path, including in-place and an existing distinct OUTPUT. New outputs and dry-run only
read the source and do not require the assertion. In every case, source/output sidecars
(`-wal`, `-shm`, `-journal`) cause refusal and are rechecked before publication, including
real paths of aliases. A newly appearing output is already protected by FileSnapshot.
Absence of sidecars is not proof of exclusive ownership; the offline assertion does
not override sidecar refusal or justify replacing a live database.

Use the existing AtomicFileTarget and acceptance/fallback policy. The parent owns
cleanup of candidate sidecars even if a supervised worker is killed. Candidate plus
its three owned sidecars count toward temporary-space checks. Cooperative progress
callbacks check budgets during SQLite work and preserve the original resource/interruption
exception rather than exposing only SQLite's generic 'interrupted' error. Native RSS/time
supervision remains the existing opt-in worker policy.

## Compatibility and limits

No third-party dependency. Report builtin mode, codec none, null level, vacuum_into
strategy and sqlite runtime version. Profiles do not tune compression; explicit levels,
other codecs and multi-thread requests fail preflight. A native stream wrapper remains
a different operation and does not compact inner tables.

There is no new total file/row cap. Catalog metadata is bounded to 4 MiB and tables to
999 columns; individual values and native allocations can exceed transfer batch sizes,
so batch_size is not a hard RSS guarantee. Unknown virtual modules/collations/functions,
encrypted/corrupt files and unverifiable row identities fail safely. Live snapshot
output and compression VFS formats remain outside this change.

Reject extension-reserved bytes per page and physical trailers/incomplete pages before
staging. SQL-value verification cannot prove retention of that opaque payload. Validate
physical size against page_size*page_count without preserving the page count itself,
which is expected to change during compaction.

## Validation

Cover fragmented and empty databases, implicit/explicit rowids, all shadowing patterns,
composite WITHOUT ROWID keys, mixed storage classes, Unicode/invalid UTF-8 TEXT, blobs,
integer/float edge values, UTF-16, sequences, indexes/checks/foreign keys, generated
columns, triggers/views, closed WAL mode, application metadata and quoted identifiers.
Inject value/type/rowid/catalog/settings corruption, new sidecars, writer/worker failure,
resource limits and source/destination mutation; assert no publication and owned cleanup.
Run existing repack suites, CLI/docs checks, examples, Ruff, Python 3.10 mypy and strict
OpenSpec validation. Record a real measured VACUUM INTO savings example.
