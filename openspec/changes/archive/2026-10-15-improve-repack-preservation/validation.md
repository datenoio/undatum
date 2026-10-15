# Implementation and acceptance evidence

## Scope and approval

The user approved implementation with “Реаплизуй эи предложения” and subsequently
requested continuation. P0–P2 are implemented. P3 items in tasks.md requested separate
follow-up proposals, now available as `add-repack-effort-trials` and
`add-native-arrow-repack`; neither capability is advertised as implemented.

## Implemented contract

- Shared `AtomicFileTarget` stages RecordSink, DuckDB COPY and every repack destination.
  Source, destination and candidate snapshots bind verified content to publication;
  failure and interruption keep old content. Cleanup failures retain the original cause.
- Dedicated streams, Parquet, typed ORC and Avro OCF adapters preserve their declared
  contracts without record inference. Complete-frame verification catches truncated
  zstd/Brotli streams tolerated by dependency readers. Gzip headers do not use stage names.
- Options/plan/result dataclasses retain the public Repacker dict boundary. Profiles,
  explicit levels, no-growth/min-savings, measured dry-run, output aliases and
  `undatum.repack/1` are wired through CLI and shared results.
- Cooperative decoded/scratch checks plus supervised worker RSS/time and cancellation
  prevent publication on budget failure. The parent controls the only commit.
- Native Parquet independently verifies physical/logical schema, field IDs, metadata,
  batch-aligned values/order, INT96 and sorting. Recovering the original serialized
  Arrow schema handles PyArrow 16 LIST-name normalization and INT96 timezone readback.
- Native ORC retains schema attributes, metadata, decimals and timestamp nanoseconds;
  union branches, old versions and unsupported LZO encoding are refused.
- Avro retains exact schema bytes, metadata, sync and encoded union branches. Blocks
  are bounded, snappy decoded size is checked before allocation, and only the
  checksum-matched Apache Avro legacy deflate trailer is tolerated.

## Automated and manual checks

- `make check-all`, using Python 3.10.20: ruff format/lint and dependency bounds pass;
  mypy ratchet 454 errors against 454 baseline (no new errors); pytest 1833 passed,
  95 skipped for absent optional features/services or opt-in memory tests.
- The isolated check environment additionally installs Click 8.5.0 for existing
  generated-tool parity tests: current Typer no longer brings it transitively, while
  those unrelated tests still import Click. This supplemental test dependency was not
  added to production requirements. Benchmark-only fastavro is installed for filerepack.
- Lower-bound direct dependencies: Python 3.10.20, iterabledata 1.0.21, PyArrow 16.0.0,
  pyorc 0.11.0, avro 1.11.3, zstandard 0.22.0, pytest 8.0.0: 88 repack tests pass.
  The fixture environment caps NumPy below 2 and uses a wheel-compatible 1.24 floor.
  Optional Brotli/Snappy adapters were installed and exercised too.
- Earlier pyorc 0.9/0.10 wheels reproduced native crashes after PyArrow 16 operations
  on macOS. pyorc 0.11 resolves the tested combination; package and conda floors agree.
- Generated CLI reference and result schema checks pass; all six executable repack
  documentation examples pass. `uv lock --check` and dependency-bound checks pass.
- Real pipeline `repack --min-savings 100` with a compatible explicit gzip output,
  followed by `count` using the named step output, succeeds and copies original bytes.
- Zstd stream and Avro zstandard with `threads=2` pass independent verification.
  Native ORC none/zlib/snappy/lz4/zstd and Parquet none/snappy/gzip/Brotli/LZ4 paths
  were exercised against actual libraries; unavailable ORC LZO is rejected in preflight.

The regressions cover identical paths, links, preflight/source/destination/candidate
mutations, writer finalization, replace/metadata/cleanup faults, interruption, malformed
and concatenated streams, empty/typed native formats, changed values/order/row counts,
dry-run, growth/fallback/migration, JSON/aliases, stdin refusal and supervised failures.

## Measurements and decisions

`benchmarks.json` contains three rotating cold repeats of nine cases: all 27 new
profile combinations preserve data and pass calibrated budgets. Comparison uses
undatum HEAD `22c15df279601dbc9acf296507f0358e44c28d48` and the modified local filerepack
checkout at `95827f3206d68760819d1a0f21ab9acfcf74313b`, with source hashes and runtime
versions in the report. Match gzip 9 / zstd 19, one thread, growth permission and
native limits. Different entry points and substantial workstation timing variance
prevent a blanket speed claim.

The previous ORC/Avro implementation fails independent preservation. Local filerepack
passes streams/Parquet/Avro but safely refuses the ORC fixture due to its writer API
error. Failed/lossy outputs are excluded from successful compression comparisons.

`benchmarks-large.json` records the 16 MiB corpus, including 131,072 native rows.
`benchmarks-layout.json` compares a larger Parquet group with smaller transfer batches:
it worsens size/time/RSS on this fixture, so retain 65,536-row defaults. Larger zstd
candidates demonstrate why a stronger profile must still satisfy no-growth policy.
Budgets in `tests/benchmarks/repack_budgets.json` are measured local 1 MiB gates, not
universal hardware claims or an automatically enabled CI job.

## Deliberate limits and reusable fixes

ZIP/7z, native Arrow/Feather, remote URI and stdin/stdout binary repack remain outside
the accepted core. ORC unions/old versions and unrepresentable Parquet profiles fail
safely. Atomic visibility does not promise fsync durability, ownership/ACL/ADS retention
or portable filesystem compare-and-swap. RSS monitoring samples every 20 ms and checks
OS high-water RSS; parent hashing/preflight is outside worker RSS but within timeout.

iterabledata registry/profile resolution is reused. Zstd complete-frame validation,
Brotli EOF validation and exception-safe codec cleanup stay in small local adapters
because they are required for repack's stricter preservation contract. They are suitable
upstream fixes; this task did not alter another repository or publish an upstream PR.

The source hashes in benchmark reports describe the measured code snapshots. The final
preflight-only LZO rejection was added after the measurements; none of those fixtures
requests LZO, and the final regression suite verifies that refusal.
