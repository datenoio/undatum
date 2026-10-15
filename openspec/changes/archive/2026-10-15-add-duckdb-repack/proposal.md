# Change: Add verified native DuckDB repacking

## Why

`undatum repack` already handles compressed byte streams and native Parquet, ORC and
Avro, but rejects an ordinary DuckDB database. `filerepack` has a conservative
implementation that copies a database into a fresh file and verifies its catalog and
typed values. Reusing that algorithm provides database compaction without converting
tables through record dictionaries or inventing a second publication mechanism.

## What Changes

- Add native DuckDB detection by the `DUCK` header at byte offset 8, including `.db`,
  `.ddb`, `.duckdb` and extensionless inputs; reject conflicting format declarations.
- Adapt `filerepack/duckdb.py`: read-only source attachment, `COPY FROM DATABASE`,
  candidate `CHECKPOINT`, catalog comparison and independent typed Arrow verification.
- Support offline databases with schemas, ordinary tables, constraints, indexes,
  defaults, comments, tags and supported primitive/nested Arrow values. Initially
  retain filerepack's bounded profile: 256 MiB physical input, 1,000,000 verified rows,
  256 MiB per side of typed verification and a 4 MiB serialized catalog.
- Refuse source/destination WAL sidecars, foreign keys, unsupported catalog objects and values,
  incompatible output formats, explicit compression levels and codecs other than
  `auto`. Use DuckDB's automatic internal compression with one engine thread.
- Reuse the current atomic destination, source/destination change guards, savings
  policy, measured dry-run, JSON result and supervised native worker. Clean up owned
  candidate WAL files on success, failure, interruption and worker termination.
- Document that DuckDB profiles use the same database-copy operation: `fast`,
  `balanced` and `max` do not select different internal compression levels. Report
  `codec=auto`, `level=null` and `strategy=copy_database` honestly.
- Record the SQLite feasibility study and a prioritized matrix of other data-file
  formats in [research.md](research.md). SQLite implementation is a separate change.

## Impact

- Affected specs: `data-repacking`, introduced by the implemented but unarchived
  `improve-repack-preservation` change. This change adds requirements rather than
  replacing that delta or the pending Arrow/Feather and effort-trial proposals.
- Affected code after approval: `undatum/common/repack_duckdb.py`, repacker detection
  and dispatch, native resource/sidecar handling, CLI help/capabilities and tests.
- Affected documentation after approval: repack command reference, changelog and
  generated references; regenerate result-schema documentation only if its descriptions
  need changing. Retain the `undatum.repack/1` field types and modes.
- No new mandatory dependency: DuckDB and PyArrow are already runtime dependencies.
  Check compatibility with their supported minimum versions before advertising support.
- Keep the filerepack BSD-3-Clause copyright, license terms and disclaimer with any
  adapted source and in distributed notices.
- Status: approved by the user on 2026-10-15 and implemented. See `validation.md` for
  measured results, checks and the foreign-key limitation discovered during integration.
