## ADDED Requirements

### Requirement: Native SQLite Compaction

The system SHALL recognize local SQLite databases by their native header and compact
supported offline files using read-only source access and VACUUM INTO a staged candidate.
It SHALL reuse atomic publication, metadata retention, measured dry-run, savings and
undatum.repack/1 results. It SHALL NOT fall back to ordinary VACUUM. SQLite >=3.31 SHALL
be required without adding a third-party runtime dependency.

#### Scenario: Fragmented SQLite database
- **WHEN** a supported SQLite database contains unused pages after deletes
- **THEN** repack creates and verifies a compact SQLite candidate
- **AND** the existing savings policy determines publication

#### Scenario: Ambiguous file name
- **WHEN** a SQLite database uses .db or no extension
- **THEN** its native header selects SQLite rather than DuckDB or a text codec

#### Scenario: Dry run or no benefit
- **WHEN** SQLite repack is requested with dry-run or its candidate provides no accepted savings
- **THEN** existing dry-run/no-benefit behavior is retained without publishing an unverified candidate

### Requirement: SQLite Semantic and Row Identity Preservation

SQLite repack SHALL independently verify schema/index/trigger/view definitions, table
layouts, all supported stored values and storage classes, hidden rowids, WITHOUT ROWID
primary-key records, sequence/statistics tables, application_id, user_version, encoding,
page_size, auto_vacuum and persistent WAL mode. Both databases SHALL pass integrity checks.
Framed typed-value verification SHALL stream without total row/file limits, preserve
raw TEXT/BLOB bytes and bind success to the finalized candidate digest. Unsupported
virtual tables, unavailable collations/functions, inaccessible rowids, catalog metadata
over 4 MiB or tables over 999 columns SHALL fail without publication.
Extension-reserved page bytes and trailing/incomplete physical pages SHALL be refused
before staging rather than silently dropped by compaction.

#### Scenario: Sparse implicit rowids and mixed storage classes
- **WHEN** SQLite tables contain sparse rowids, INTEGER/REAL/TEXT/BLOB/NULL values or invalid UTF-8 TEXT
- **THEN** verification retains row identities, raw values and their storage classes

#### Scenario: Composite primary key without rowid
- **WHEN** a supported WITHOUT ROWID table uses a composite primary key
- **THEN** all records are verified in canonical key order without inventing rowids

#### Scenario: Closed WAL-mode database
- **WHEN** an offline database retains persistent WAL mode but has no active sidecars
- **THEN** the candidate retains that persistent mode after compaction and verification

#### Scenario: Changed candidate
- **WHEN** a readable candidate changes a value, storage class, rowid, catalog object or significant setting
- **THEN** verification refuses publication and preserves source and prior destination

#### Scenario: Opaque physical payload
- **WHEN** a SQLite file contains extension-reserved page bytes or data beyond complete database pages
- **THEN** repack refuses that physical profile before candidate creation
- **AND** the original file remains unchanged

### Requirement: SQLite Offline Replacement and Sidecar Ownership

Replacing an existing SQLite repack destination SHALL require sqlite_offline=True or
--sqlite-offline as an assertion that database users are closed. A new distinct output
and dry-run SHALL not require that replacement assertion. Source/output WAL, SHM and
journal sidecars SHALL always cause refusal, including when newly detected before
publication or beside a resolved source alias. The assertion SHALL NOT override sidecar
guards or imply that missing sidecars establish exclusive ownership. Only owned
candidate sidecars SHALL be cleaned, including after worker failure or interruption;
candidate plus sidecars SHALL count toward temporary-space accounting.

#### Scenario: In-place replacement without offline assertion
- **WHEN** native SQLite repack would replace an existing path without sqlite_offline
- **THEN** it reports the required assertion before staging and leaves existing files unchanged

#### Scenario: New output or measured dry run
- **WHEN** SQLite repack writes a new distinct output or performs dry-run without active sidecars
- **THEN** it can encode and verify without the replacement assertion

#### Scenario: Existing sidecar or concurrent sidecar
- **WHEN** source/output has a WAL, SHM or journal before preflight or gains one before publication
- **THEN** repack refuses publication and never deletes that source/output sidecar

#### Scenario: Worker failure
- **WHEN** a SQLite worker exceeds a budget, is interrupted or fails during writing
- **THEN** no candidate is published and the parent removes its owned file and sidecars

### Requirement: SQLite Compaction Controls

Native SQLite repack SHALL accept omitted compression, auto or none and report codec
none, level null, a vacuum_into strategy and the SQLite runtime version. All shared
profiles SHALL use the same compaction operation. Explicit levels, unsupported codecs,
multiple threads and incompatible output format declarations SHALL fail before staging.
Outer-compressed SQLite files SHALL remain byte-stream repacks without inner compaction.

#### Scenario: Unsupported codec or level
- **WHEN** native SQLite repack requests zstd, an explicit level or multiple threads
- **THEN** a validation error is returned before candidate creation

#### Scenario: Outer compressed database
- **WHEN** a SQLite database is already wrapped in gzip and is stream-repacked
- **THEN** its decoded database bytes are preserved without compacting tables
