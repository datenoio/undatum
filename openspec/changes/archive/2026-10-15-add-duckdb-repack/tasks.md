## 1. Research and review

- [x] 1.1 Inspect the preserving repack core, related active proposals and local filerepack.
- [x] 1.2 Reproduce DuckDB compaction and typed verification on a temporary database.
- [x] 1.3 Assess SQLite compaction, WAL snapshots and other data-file compression formats.
- [x] 1.4 Obtain review/approval of this proposal before implementing the capability.

## 2. Implementation after approval

- [x] 2.1 Confirm minimum DuckDB/PyArrow catalog, COPY and typed-reader APIs; preserve
  the filerepack BSD-3-Clause notice for adapted code.
- [x] 2.2 Add native DuckDB detection and preflight for output, options, catalog/types,
  bounds and offline sidecar requirements.
- [x] 2.3 Add the bounded native COPY/CHECKPOINT adapter and independent catalog/typed
  verification using the existing Arrow value comparator and candidate digest proof.
- [x] 2.4 Integrate dispatch, existing acceptance/dry-run/results and parent-owned
  candidate-sidecar cleanup, including aggregate scratch and worker termination.

## 3. Verification and public documentation

- [x] 3.1 Add semantic fixtures, no-benefit/dry-run/empty cases and corruption,
  concurrency, unsupported-profile, resource-limit and cleanup regression tests.
- [x] 3.2 Update repack documentation, CLI help/capabilities and CHANGELOG; regenerate
  CLI references and any affected result-schema descriptions.
- [x] 3.3 Run relevant repack, convention and documentation checks, Ruff and the Python
  3.10 mypy ratchet; record the minimum-version API checks and measured fixture savings.

## 4. Proposal validation

- [x] 4.1 Validate `add-duckdb-repack` with OpenSpec strict mode and review the delta for
  compatibility with the unarchived preserving core and pending Arrow/effort proposals.
