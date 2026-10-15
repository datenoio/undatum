## 1. P0 — Safe publication and regression containment

- [x] 1.1 Add regressions for explicit same INPUT/OUTPUT, empty Parquet, existing OUTPUT
  preservation after truncated input/write/close failure, and current ORC/Avro data loss.
- [x] 1.2 Extract/reuse a shared staged atomic-file target with deferred commit in the
  common writer layer; preserve RecordSink and DuckDB COPY behavior.
- [x] 1.3 Stage every repack destination, recognize same-file aliases, close resources
  reliably and clean candidates on all exception/interruption paths.
- [x] 1.4 Initialize empty native Parquet from original schema and reject invalid
  or missing candidates before publication.
- [x] 1.5 Contain unsafe generic ORC/Avro conversion until preserving adapters are ready;
  return a typed error rather than publishing a coerced/partial result.

## 2. P0–P1 — Format preservation and preflight

- [x] 2.1 Add typed options/plan/result dataclasses with a backward-compatible Repacker
  dict-return boundary; resolve capabilities before allocating output.
- [x] 2.2 Detect codec independently from datatype; validate magic/suffix/override,
  context-specific aliases and level/profile capabilities.
- [x] 2.3 Add verified stream payload length/hash/read-back with complete EOF/trailer
  validation, deterministic non-temp gzip headers and concatenated-frame coverage.
- [x] 2.4 Add native Parquet schema/metadata/physical compatibility and aligned batch
  value/order verification, including nested NaNs, signed zero, decimals and timestamps.
- [x] 2.5 Implement preserving typed ORC reader/writer with schema/user metadata,
  correct empty output and error propagation; refuse unrepresentable profiles.
- [x] 2.6 Implement preserving Avro OCF block recompression with original schema bytes,
  union encodings, metadata, sync markers, counts/order and native validation.
- [x] 2.7 Add source/candidate/existing-destination snapshots, generation rechecks,
  mode/mtime/xattr preservation and explicit linked/non-regular file policy.
- [x] 2.8 Reject unsupported ZIP/7z operations and incompatible native/outer-codec
  combinations before writing, with actionable UndatumError diagnostics.
- [x] 2.9 Verify all new format APIs against lower-bound dependency versions,
  especially PyArrow 16; contribute reusable codec fixes to iterabledata where practical.

## 3. P1 — User controls and outcomes

- [x] 3.1 Implement no-growth/min-savings/allow-grow policy and distinguish optimization
  from explicit codec migration or raw wrapping.
- [x] 3.2 Implement distinct-output original-copy fallback for no-benefit optimization
  and verify pipeline artifact compatibility; never copy across different codecs.
- [x] 3.3 Implement measured --dry-run with full encoding/verification and no publication.
- [x] 3.4 Add --profile fast|balanced|max, effective codec settings and explicit-level
  precedence; preserve default max and existing options/positional output.
- [x] 3.5 Add CLI summary and versioned undatum.repack/1 through common.results.emit();
  keep JSON stdout clean and map errors to existing exit codes.
- [x] 3.6 Add canonical --output/-o alias with conflicting positional-output validation;
  cover CLI/API/non-TTY/progress compatibility.
- [x] 3.7 Update CHANGELOG, repack docs/capabilities, generated CLI reference and result
  schemas; document behavior changes and measured dry-run cost.

## 4. P2 — Resource controls and measured tuning

- [x] 4.1 Add validated decoded-byte/scratch/time/cancellation budgets and report actual
  usage; distinguish cooperative limits from hard native process limits.
- [x] 4.2 Implement worker isolation/monitoring where hard native RSS/time limits are
  requested; verify abort leaves original/prior output intact.
- [x] 4.3 Build a representative repack benchmark corpus and collect physical size,
  encode/verify wall time, process-tree RSS, scratch, decode and downstream scan time.
- [x] 4.4 Compare undatum baseline and filerepack with equivalent codec/settings/fidelity;
  calibrate benchmark budgets from measurements, with source and environment provenance.
- [x] 4.5 Tune batch/row-group size and optional codec threads without unbounded group
  accumulation or loss of metadata/fidelity; gate changes on benchmark results.
- [x] 4.6 Run targeted regressions, make check-all, Python 3.10 mypy, lower-bound dependency
  checks, generated-doc checks and repack documentation examples.

## 5. Follow-up proposals after core acceptance

- [x] 5.1 Propose bounded opt-in high-effort candidate trials with verified baseline,
  optional pigz/strong gzip/zstd/XZ paths and measured size/time/resource trade-offs.
- [x] 5.2 Propose native Arrow IPC/Feather repack preserving framing/schema/batch metadata;
  keep ZIP/7z archive preservation and other new formats in separate proposals.

## 6. Proposal validation

- [x] 6.1 Run openspec validate improve-repack-preservation --strict and review proposal
  boundaries against concurrent streaming-core and machine-readable-output changes.
- [x] 6.2 Obtain proposal approval before production implementation begins.

Implementation and validation evidence: [validation.md](validation.md).
