## ADDED Requirements

### Requirement: Native DuckDB Compaction

The system SHALL support repacking an offline local DuckDB file by recognizing its
native signature, attaching the source read-only, copying its supported catalog and
data into a fresh candidate with `COPY FROM DATABASE`, and checkpointing the candidate.
It SHALL use the existing verified atomic publication, metadata, acceptance, dry-run
and result contracts. Native DuckDB output SHALL remain a DuckDB database.

#### Scenario: Fragmented database
- **WHEN** a supported offline DuckDB file contains space left by deleted records
- **THEN** repack creates and verifies a fresh database candidate
- **AND** it publishes the candidate only under the existing savings/growth policy

#### Scenario: DuckDB with an ambiguous extension
- **WHEN** a valid DuckDB database is named `warehouse.db` or has no extension
- **THEN** its DuckDB header selects native database repacking
- **AND** a SQLite file is not treated as DuckDB merely because its name ends in `.db`

#### Scenario: No benefit with a distinct output
- **WHEN** the candidate is not smaller and growth was not allowed for a distinct output
- **THEN** the original database is copied atomically to that output
- **AND** the result distinguishes the rejected candidate from the published original

#### Scenario: Measured database dry run
- **WHEN** native DuckDB repack is requested with `--dry-run`
- **THEN** a real candidate is encoded and verified and its measured size is reported
- **AND** source and prior output remain unchanged and owned candidates are removed

### Requirement: DuckDB Catalog and Typed Value Preservation

Native DuckDB repack SHALL independently compare supported schemas, table definitions,
constraints, indexes, defaults, comments/tags, Arrow schemas and all table values in
bounded aligned batches. Verification SHALL include nested nulls, floating-point bit
patterns, decimal precision and nanosecond timestamps and SHALL be bound to the finalized
candidate digest. Unsupported catalog objects, types or bounds SHALL fail without
publication. Initial supported bounds SHALL be documented as 256 MiB physical input,
1,000,000 total verified rows, 256 MiB typed values per side and a 4 MiB catalog.

#### Scenario: Typed nested data
- **WHEN** supported tables contain nested NaNs, signed zero, decimals and nanosecond timestamps
- **THEN** the candidate retains the original supported types, values and compared scan order
- **AND** differing transfer batch boundaries do not alter the verification result

#### Scenario: Changed candidate
- **WHEN** a candidate changes a table value, constraint, index or significant catalog metadata
- **THEN** independent verification refuses publication
- **AND** source and prior output retain their original bytes

#### Scenario: Empty database or table
- **WHEN** a supported database has no user tables or contains zero-row tables
- **THEN** any published candidate is a valid database with its supported catalog preserved

#### Scenario: Unsupported database profile
- **WHEN** a database contains foreign keys, views, sequences, macros/functions, custom types, unsupported values or exceeds supported bounds
- **THEN** the command reports the unsupported profile without publishing a candidate

### Requirement: DuckDB Offline Guards and Candidate Sidecars

DuckDB repack SHALL refuse source or existing-destination WAL sidecars and recheck them
before publication. It SHALL use read-only source attachment, disable automatic
extension installation/loading and disable external access before evaluating database
objects. All connections SHALL close before replacement. Owned candidate sidecars
SHALL be removed after success, error, interruption or worker termination; source and
destination sidecars SHALL NOT be deleted. Requested scratch limits SHALL account for
the candidate and its owned WAL. The documented contract SHALL require closed database
users and SHALL NOT claim that a missing WAL establishes exclusive ownership.

#### Scenario: Pending WAL
- **WHEN** source or existing output has a `.wal` sidecar before preflight
- **THEN** repack refuses the database without modifying it or deleting its WAL

#### Scenario: WAL appears during repack
- **WHEN** a source or destination WAL appears after preflight but before publication
- **THEN** publication is aborted and the database and its WAL are left intact

#### Scenario: Native worker is terminated
- **WHEN** memory, scratch or timeout enforcement terminates a database worker
- **THEN** the parent removes the owned candidate and its WAL without publishing

### Requirement: DuckDB Automatic Compression Controls

Native DuckDB repack SHALL use the engine's automatic compression with a single thread
and report `codec=auto`, `level=null` and the database-copy strategy. Omitted compression
or `auto` SHALL be accepted; explicit levels, unsupported codecs, thread counts and
incompatible output declarations SHALL fail before writing. Shared profiles SHALL be
documented as selecting the same database-copy strategy for DuckDB, without promising
different compression effort or a maximum ratio. Existing `undatum.repack/1` field types
and modes SHALL remain compatible.

#### Scenario: Automatic compression
- **WHEN** a supported DuckDB file is repacked with default settings or `--compression auto`
- **THEN** DuckDB chooses its internal compression and the result describes that strategy

#### Scenario: Unsupported database compression setting
- **WHEN** native DuckDB repack is requested with `--level 9` or `--compression zstd`
- **THEN** a validation error is raised before candidate creation
- **AND** the option is not silently ignored or applied as an outer wrapper

#### Scenario: Conflicting output format
- **WHEN** a native DuckDB input is assigned an output declaring CSV, SQLite or outer gzip compression
- **THEN** the command rejects the conflicting destination before writing
