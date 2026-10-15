## ADDED Requirements

### Requirement: Format Preserving Repacking
The system SHALL provide local-file repacking that preserves the data format and
decoded content. Stream repacking SHALL preserve exact decoded bytes; native
Parquet, ORC and Avro repacking SHALL preserve values, row order, types and significant
schema/file metadata. Inputs that cannot meet the preservation contract SHALL be
refused without publishing a changed file.

#### Scenario: Byte preserving CSV stream
- **WHEN** a gzip-compressed CSV with BOM, CRLF and quoted fields is repacked
- **THEN** the output decodes to exactly the original byte sequence
- **AND** parsing or normalizing records is not required

#### Scenario: Typed native ORC and Avro
- **WHEN** native ORC or Avro containing integers, booleans, decimals and nested values is repacked
- **THEN** original types, values, row order and significant metadata are preserved
- **AND** values are not coerced to strings or written through inferred string schemas

#### Scenario: Unsupported preservation profile
- **WHEN** a native input contains metadata or physical representations the selected backend cannot preserve
- **THEN** the operation reports the unsupported profile before publication
- **AND** the source and any prior destination remain unchanged

### Requirement: Staged Atomic Publication
Every local repack destination SHALL be written through the shared staged atomic-file
mechanism. Same-file aliases SHALL be recognized, and encoder, finalization,
verification or publication failures SHALL leave the source and any prior destination
content intact. Atomic visibility SHALL NOT imply crash durability.

#### Scenario: Explicit same file output
- **WHEN** INPUT and explicit OUTPUT refer to the same ordinary file
- **THEN** repack uses a sibling candidate and verifies it before atomic replacement
- **AND** opening the writer does not truncate the input

#### Scenario: Failure with existing distinct output
- **WHEN** decoding a truncated source fails while a distinct OUTPUT already exists
- **THEN** the prior OUTPUT bytes are preserved
- **AND** all owned temporary candidates are removed

#### Scenario: Writer finalization error
- **WHEN** encoder close or finalize fails after writing candidate bytes
- **THEN** the candidate is not published and the operation fails with its original cause
- **AND** remaining readers and temporary resources are cleaned up

### Requirement: Filesystem Preservation and Change Detection
The system SHALL preserve mode, modification time and supported extended attributes
according to its declared filesystem contract. It SHALL check source, candidate and
existing-destination identity/generation before publication and refuse detected
concurrent modification. In-place symbolic links and multiply hard-linked sources
SHALL be refused; supported distinct-output copies MAY read linked sources.

#### Scenario: Source permissions survive replacement
- **WHEN** a regular file with mode 0644 and a known modification time is repacked in place
- **THEN** the published file retains that mode and modification time

#### Scenario: Changed source or destination
- **WHEN** the source or existing destination changes after preflight and before publication
- **THEN** the operation reports a conflict and does not overwrite the changed file

#### Scenario: Candidate changes after verification
- **WHEN** a candidate changes after its preservation check
- **THEN** publication is refused
- **AND** an old verification result is not accepted for the changed candidate

#### Scenario: In place symbolic link
- **WHEN** an in-place operation targets a symbolic link or a source with multiple hard links
- **THEN** the operation is refused before candidate encoding

### Requirement: Independent Candidate Verification
Publication SHALL require successful candidate structural and preservation verification
bound to that candidate. Stream verification SHALL validate complete decode, decoded
length and content digest. Native verification SHALL compare schemas, metadata,
values and order without loading the entire dataset into memory.

#### Scenario: Corrupted candidate
- **WHEN** an encoder produces a readable candidate with changed values or missing rows
- **THEN** independent preservation verification fails
- **AND** the candidate does not replace source or destination

#### Scenario: Concatenated stream frames
- **WHEN** a supported compressed input contains multiple concatenated frames or members
- **THEN** the entire decoded content is preserved or the input is safely refused
- **AND** verification cannot succeed after reading only the first frame

### Requirement: Native Parquet Preservation
Parquet repack SHALL produce valid output for empty and populated files, preserve
logical and supported physical schemas, field identifiers and significant metadata,
and independently verify values and row order. Compression and documented layout
changes MAY differ; unsupported sorting declarations, external chunks or physical
representations SHALL NOT be silently removed or changed.

#### Scenario: Empty Parquet
- **WHEN** a zero-row Parquet file is repacked
- **THEN** any published output is a valid Parquet file with the original schema and metadata
- **AND** a zero-byte temporary file is never published

#### Scenario: Physical compatibility
- **WHEN** an input uses INT96 timestamps or sorting declarations
- **THEN** those properties are preserved by a verified path or the operation is refused
- **AND** successful output does not silently change physical compatibility

#### Scenario: Floating point and nested values
- **WHEN** Parquet includes nested NaNs, signed zero, decimals and timestamp timezones
- **THEN** verification preserves the relevant bit patterns, precision, scale and timezone
- **AND** different batch boundaries do not change row order or equality results

### Requirement: Native Avro Block Preservation
Avro repacking SHALL preserve original schema bytes, significant custom metadata,
sync identity, encoded record semantics including union branch choices, record count
and order while changing the selected block compression. It SHALL validate block
lengths, sync markers, complete input and a native read-back.

#### Scenario: Ambiguous union branches
- **WHEN** an Avro record selects the long branch of an int-or-long union
- **THEN** repacking retains that encoded branch choice and original schema identity
- **AND** no record inference or string coercion changes it

#### Scenario: Avro custom metadata
- **WHEN** Avro contains application metadata and a fixed sync marker
- **THEN** those are retained while the compression codec metadata changes as requested

### Requirement: Preflight Compression Capabilities
The system SHALL resolve envelope codec separately from data format and validate
codec aliases, supported levels, output compatibility and required dependencies
before writing. Unsupported ZIP/7z stream-style repacking SHALL be refused until
a preserving archive contract is implemented.

#### Scenario: Codec independent of datatype
- **WHEN** a supported stream codec is recognized but the inner data format is unknown
- **THEN** repack can select that stream codec without requiring datatype detection success
- **AND** detection errors are not silently treated as an uncompressed input

#### Scenario: Conflicting native output suffix
- **WHEN** native Parquet input is assigned an outer-compressed OUTPUT without a supported wrapper mode
- **THEN** repack reports an incompatible destination before writing
- **AND** it does not create bare Parquet under a gzip suffix

#### Scenario: Outer codec migration
- **WHEN** a user requests a different outer codec
- **THEN** a distinct compatible output path is required
- **AND** in-place rewriting under a stale codec suffix is refused

#### Scenario: Unsupported level
- **WHEN** --level is supplied to a backend that cannot honor it or outside its valid range
- **THEN** the operation reports a ValidationError before writing
- **AND** the option is not silently ignored

### Requirement: Savings Aware Acceptance
For same-representation optimization, repack SHALL retain the original representation
unless the verified candidate is strictly smaller and meets the requested percentage
savings threshold, or growth is explicitly allowed. Explicit outer-codec migration
and raw wrapping SHALL honor the requested target representation rather than copying
incompatible source bytes. Growth permission SHALL NOT disable preservation checks.

#### Scenario: No benefit in place
- **WHEN** a verified same-representation candidate is equal in size or larger and growth is not allowed
- **THEN** source bytes remain unchanged and the result reports unchanged with no_benefit

#### Scenario: No benefit with distinct compatible output
- **WHEN** a same-representation optimization with a distinct OUTPUT produces no acceptable candidate
- **THEN** the original is atomically copied to the requested OUTPUT
- **AND** the result distinguishes candidate size, final size and unchanged content

#### Scenario: Migration grows
- **WHEN** explicit gzip-to-zstd migration produces a larger verified zstd file without an explicit savings threshold
- **THEN** the requested zstd candidate is published and negative savings are reported
- **AND** gzip bytes are not copied under the zstd suffix

#### Scenario: Explicit savings threshold rejects migration
- **WHEN** explicit migration fails an explicitly requested min-savings threshold
- **THEN** no candidate is published and the result reports skipped with below_min_savings

### Requirement: Measured Dry Run
Repack SHALL provide --dry-run that encodes and verifies a candidate and reports
measured candidate sizes and acceptance decisions without publishing output or
modifying source, existing destination or backups. Owned candidates SHALL be cleaned up.

#### Scenario: Dry run with existing output
- **WHEN** repack is run with --dry-run and an existing OUTPUT
- **THEN** original source and destination bytes remain unchanged
- **AND** the result reports measured candidate size and published=false

### Requirement: Compression Profiles and Stable Results
Repack SHALL support fast, balanced and max profiles with default max, codec-specific
effective settings and explicit-level precedence. It SHALL retain existing CLI
arguments and the Repacker dict-return boundary. --json SHALL emit one versioned
undatum.repack/1 result through the shared results layer with sizes, status, reason,
savings, settings, verification and publication information.

#### Scenario: Explicit level wins
- **WHEN** a supported explicit level and a profile are supplied
- **THEN** the explicit level is applied and reported in effective settings

#### Scenario: Machine readable summary
- **WHEN** repack runs with --json
- **THEN** stdout contains exactly one undatum.repack/1 JSON document
- **AND** progress and diagnostics do not contaminate stdout

#### Scenario: Existing output argument compatibility
- **WHEN** an existing invocation uses positional OUTPUT
- **THEN** it remains accepted
- **AND** conflicting positional OUTPUT and --output values are refused

### Requirement: Bounded Resources and Honest Guarantees
Stream repacking SHALL avoid materializing the complete decoded payload by default.
The system SHALL support validated decoded-byte, scratch and time budgets with
cancellation and safe abort. Hard native memory/time guarantees SHALL require
effective process monitoring or equivalent enforcement, and SHALL NOT be inferred
from Python transfer-buffer or batch-row sizes alone.

#### Scenario: Decoded byte limit exceeded
- **WHEN** decode exceeds an explicitly configured decoded-byte budget
- **THEN** the operation stops without publication and reports the exceeded limit

#### Scenario: Native memory limit
- **WHEN** hard memory limits are requested for a native codec operation
- **THEN** native allocations are monitored/enforced or the unsupported guarantee is refused before encoding
- **AND** the command does not present a cooperative batch-size check as a hard RSS bound

#### Scenario: Interrupted operation
- **WHEN** a user interrupts encoding or verification
- **THEN** no candidate is published, owned temporary resources are cleaned up and CLI exits 130
