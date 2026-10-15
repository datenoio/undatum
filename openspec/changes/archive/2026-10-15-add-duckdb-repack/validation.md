# DuckDB repack validation

Completed on 2026-10-15 after the user explicitly approved implementation in this chat.

## Implemented behavior

- Native DuckDB signature detection, including `.db`, `.ddb`, `.duckdb`, unknown and
  absent suffixes; incompatible format/output/codec/level/thread requests fail preflight.
- Offline read-only source, disabled extension autoload/install and external access,
  native `COPY FROM DATABASE`/`CHECKPOINT` and independent catalog/typed Arrow verification.
- Existing atomic publication, metadata retention, no-benefit fallback, savings policy,
  dry-run, JSON result, timeout/RSS supervision and decoded/scratch budgets.
- Source/destination WAL guards, including real paths of linked inputs and checks at
  publication; parent-owned candidate WAL cleanup also covers worker failure.
- Bounded filerepack profile, honest `auto` compression/strategy reporting, CLI reference,
  command documentation, changelog and distributed BSD-3-Clause attribution.

## Checks and environments

| Check | Result |
|---|---|
| Native suite, Python 3.13.7 / DuckDB 1.5.4 / PyArrow 25.0.0 | 55 passed |
| Repack, preservation, resources, native, CLI conventions and docs combined | 148 passed, 4 skipped before the last three dependency/finalization cases were added; those three also pass in the final native suite |
| Native suite, Python 3.10.20 / DuckDB 1.3.0 / PyArrow 16.0.0 / NumPy 1.26.4 | 52 passed; the final three dependency/finalization cases were added afterward |
| Python 3.10.20 mypy ratchet, full locked dev environment | 454 errors, baseline 454; no increases and no new common-module errors |
| Ruff lint and format on touched Python files | Passed |
| Dependency bound validation | Passed; no dependency version increase |
| Generated CLI reference / command documentation checks | Passed; repack page regenerated |
| Executable repack documentation examples | 6/6 passed |
| Built distribution attribution | `THIRD_PARTY_NOTICES` is present in License-File metadata and installed dist-info/licenses |
| OpenSpec strict validation | Passed |

The four optional-codec skips are pre-existing environment skips in preservation tests.
The main environment reports third-party qddate/Pyparsing deprecations; no test fails.
The mypy check was run with the complete locked dev dependencies, matching the project's
required Python 3.10 workflow. An earlier intentionally minimal mypy environment lacked
runtime packages/stubs and was replaced for the authoritative check. Minimum-version
database testing was separate from the locked-version mypy check.

Native regressions cover schemas/constraints/defaults, indexes/comments, decimals,
nanosecond timestamps, nested float bits, NULL and BLOB values, quoted schema names,
empty databases/tables, different batch boundaries, same/distinct outputs, dry-run,
savings rejection, unsupported objects/types/settings, malformed names/headers, WAL
changes, worker cleanup, limits, locked databases, missing backends and writer close
failure. Deliberately changed catalog/data candidates never publish.

## Measured comparison with filerepack

The exact measurements and successful independent filerepack read-back are recorded in
[benchmark.json](benchmark.json). Both implementations processed the same fragmented
fixture from `tests/test_repack_duckdb.py::database(fragmented=True)`.

| Item | Bytes |
|---|---:|
| Original database | 16,265,216 |
| undatum candidate | 1,585,152 |
| filerepack candidate | 1,585,152 |

Savings were **90.2543%** on this deliberately fragmented fixture. filerepack's own
`verify_duckdb` accepted the undatum output and its reference output. This is one
mechanism/fidelity comparison, not a representative compression-ratio or throughput
guarantee. Timings and observed scratch are retained in the JSON evidence.

## Known limits

- Input up to 256 MiB, at most 1,000,000 total verified rows, 256 MiB typed values per
  verification side and a 4 MiB serialized catalog. Native engine memory is limited
  separately from process RSS; hard worker monitoring remains opt-in.
- Foreign keys are explicitly refused before staging. The native database-copy
  operation reproduced a foreign-key load-order failure on DuckDB 1.5.4, so the adapter
  does not advertise arbitrary constraint graphs. Primary/unique/check/not-null
  constraints and defaults are retained by the supported path.
- Views, sequences, macros/functions, custom types and unsupported Arrow types are
  refused. Storage layout/version can change according to the DuckDB runtime.
- Database users must be closed. Filesystem guards and absent WALs do not establish an
  exclusive lock against a user opening the database during atomic replacement.
- SQLite, native Arrow/Feather and other formats remain researched follow-ups, as
  documented in [research.md](research.md); they are not newly advertised capabilities.
