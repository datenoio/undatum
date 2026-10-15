# Native DuckDB repack design

## Context

The working tree already contains the implemented preserving-repack change, including
`AtomicFileTarget`, `FileSnapshot`, `RepackBudget`, a supervised worker and the
`undatum.repack/1` result. Those changes and other unrelated local edits must be
preserved. The new adapter belongs beside the Parquet/ORC and Avro adapters.

The source algorithm is the local filerepack checkout at commit
`95827f3206d68760819d1a0f21ab9acfcf74313b`, file `filerepack/duckdb.py`, SHA-256
`773bfce1f84a1895760ba49ecc370b3a0bef85f4513188a0939b762feef04af2`.

## Decisions

### 1. Detect the database separately from its name and outer compression

Recognize the native signature at offset 8. `.db` is ambiguous and must never by
itself imply either DuckDB or SQLite. A `.duckdb`/`.ddb` declaration with an invalid
header fails before allocating output; a real DuckDB file named as another known data
format also fails. A valid DuckDB file with an unknown or absent suffix is supported.

Output can retain a DuckDB/ambiguous/unknown suffix but cannot claim a different
known data format or an outer codec. Existing outer-compressed database inputs stay
on the byte-stream path: recompressing `db.duckdb.gz` preserves its decoded database
bytes and does not recursively compact its tables.

### 2. Port the database-copy algorithm, not filerepack's surrounding lifecycle

The adapter uses a private in-memory DuckDB coordinator. Disable extension auto-install
and autoload; attach the source read-only and the candidate writable using escaped
SQL literals. Then disable external access before querying database-supplied objects
or copying data. Use a single engine thread and disable spill in the initial bounded
profile, as filerepack does.

Preflight the supported catalog and typed data before executing `COPY FROM DATABASE
checked TO candidate`; finish with `CHECKPOINT candidate` and close all connections
before independent verification and publication. The current atomic target supplies
an absent staged path; also accept an allocated empty file by removing it before
attachment because DuckDB expects an absent path or a valid database.
Keep its pathname under the existing `AtomicFileTarget` ownership.

Do not use DuckDB `VACUUM` as the compaction algorithm, export SQL scripts, or rebuild
individual tables with inferred schemas. Unsupported views, sequences, macros/functions,
foreign keys, custom types, extension-dependent values and Arrow types outside filerepack's allowlist
are refused. The first release deliberately keeps the existing conservative limits;
removing them requires a separate measured streaming design.

Integration found that DuckDB 1.5.4's `COPY FROM DATABASE` can load a referencing table
before referenced rows and fail a foreign-key constraint. Reject foreign keys during
catalog preflight instead of silently dropping constraints or substituting a different
copy algorithm. Primary keys, unique/check/not-null constraints and defaults remain
within the supported profile.

### 3. Verify both catalog semantics and typed ordered values

Compare schemas, tables, table SQL (including constraints), indexes, column definitions,
defaults, comments and tags. Reopen source and candidate independently with read-only
attachments and the same restrictions. Compare Arrow schemas and bounded table batches,
aligning slices when reader batch boundaries differ. Reuse
`repack_columnar.arrow_values_equal()` to preserve nested nulls, decimal precision,
nanosecond timestamps, NaNs and signed floating-point zero.

Retain filerepack's catalog/logical fingerprint as an additional check if useful, but
never accept the sorted VARCHAR-row fingerprint alone: it cannot replace typed/order
verification. Bind successful verification to the finalized candidate's SHA-256 using
the current publication proof. Empty databases and empty supported tables remain
valid. No SQL row ordering beyond the compared sequential scan is newly promised;
databases do not provide a general implicit `ORDER BY` guarantee.

### 4. Keep offline publication and native scratch under the shared policy

Refuse any source or existing destination `.wal` before opening a database and recheck
before publication. A newly appearing WAL aborts the operation. Explain that callers
must close database users; a missing WAL and filesystem snapshots do not establish
exclusive ownership against a connection opening during replacement.

Only delete sidecars owned by the candidate; never delete source/destination sidecars.
Parent-side cleanup must cover a candidate `.wal` left by a forcibly terminated worker.
Account for candidate plus owned WAL scratch in database budget checks and worker
supervision. A coarse transfer batch size alone cannot enforce native RSS or interrupt
a blocking `COPY`; retain the existing process monitor for memory/time guarantees.
Tighter explicit budgets take precedence over the bounded adapter defaults.

Use existing `mode=builtin`, `migration=false`, savings acceptance, metadata retention
and dry-run behavior. A non-beneficial distinct output receives the unchanged source
through the existing atomic fallback, subject to the same sidecar guards. `rows` is
the sum of verified table rows and logical-byte accounting is the actual verification
work, including both sides, rather than an estimate from the physical database size.

### 5. Describe automatic compression accurately

The copy operation lets DuckDB choose its native compression. Accept omitted
`--compression` and `--compression auto`; reject `zstd`, `gzip`, etc. and any explicit
`--level` before writing. Keep `--threads 1` for this initial profile. All three shared
profiles perform the same database-copy strategy and must be documented/reported as
such; never claim a zstd level, effort search or maximum attainable compression.

Retain `codec=auto`, `level=null` and add the strategy within `effective_settings`.
Physical layout and the candidate's storage version are selected by the DuckDB runtime;
byte identity and compatibility with every older DuckDB reader are not guaranteed.
Report the runtime version in verification details. Confirm actual API support on the
project's minimum DuckDB/PyArrow versions; unsupported APIs cause an actionable feature
error rather than an unexplained internal exception or a global dependency increase.

### 6. Keep SQLite and other formats as researched follow-ups

SQLite compaction needs a separate preservation and live-snapshot contract. Do not
advertise SQLite, Arrow, HDF5 or ZIP-based formats as implemented by adding their names
to the detection table. See [research.md](research.md) for mechanisms and priorities.

## Validation

- Match filerepack on fragmented DuckDB fixtures and compare schemas, constraints,
  defaults, indexes, comments/tags and typed content, including nested float bits.
- Exercise in-place, explicit same path, distinct output, dry-run, no benefit, growth,
  savings threshold, empty databases/tables, unknown suffixes and quoted identifiers.
- Inject value/catalog corruption, source/destination mutation and a newly appearing
  WAL; assert unchanged published bytes and candidate/owned-sidecar cleanup.
- Reject unsupported catalog objects/types, bounds, incompatible names/codecs/levels
  and a locked database. Cover native-worker termination and scratch/RSS/time limits.
- Run the repack and CLI convention suites, generated-doc checks, examples, Ruff and
  the Python 3.10 mypy ratchet. Check minimum DuckDB/PyArrow APIs separately.

## Risks and trade-offs

- Conservative bounds exclude large databases: publish those limits prominently;
  do not imply that batch verification removes native engine allocation limits.
- Recompression may save nothing or grow an already compact database: the existing
  acceptance policy preserves the original unless growth was explicitly requested.
- New runtime storage choices may alter reader compatibility: report the runtime and
  document the limit instead of claiming a byte/physical-format preserving rewrite.
- Adapted filerepack code carries BSD-3-Clause attribution obligations: retain its full
  notice in source/distributions without changing undatum's overall MIT license.
