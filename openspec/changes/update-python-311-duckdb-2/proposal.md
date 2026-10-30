# Change: Move to Python 3.11+ and the DuckDB 2.0 LTS Line

## Why
Python 3.10 reached end of life in October 2026, and the support policy (`openspec/project.md`,
`CONTRIBUTING.md`) drops a version in the first minor release after its end of life. The same
month DuckDB 2.0.0 (LTS, 2026-10-21, supported until October 2027) shipped, and the current
releases of DuckDB, pandas (3.1), pyarrow (26) and Polars (2.x) all require Python 3.11 or
newer; on 3.10 pip silently installs their older lines.

undatum pins `duckdb>=1.3,<2`, so it stays on the 1.5 line (supported until 2027-03-01; the
1.4 LTS line ends on 2026-11-17). Moving to DuckDB 2.0 also unblocks the engine work in
`refactor-duckdb-first-execution`, which relies on the 2.0 relation-to-Arrow API.

DuckDB 2.0 changes Python APIs that undatum uses or may use. Arrow export (`fetch_record_batch`,
`fetch_arrow_table`, `arrow()`, `pl()`) is removed from `execute()` results, and the default
Arrow batch shrinks to 131,072 rows. Sharing one connection across threads raises
`ResourceInUseException`. `write_csv(overwrite=False)` raises when the file exists. Evidence:
`dev/docs/ENGINE_AND_COMPETITOR_REVIEW_2026-10-28.md` (section 5.1).

## What Changes
- **BREAKING**: `requires-python = ">=3.11"`; classifiers list 3.11–3.13 (3.14 once every base
  dependency publishes wheels). The CI matrices (`ci.yml`, install gate, lowest-dependency job),
  ruff `target-version = "py311"` and mypy `python_version = "3.11"` follow. Users on 3.10 keep
  receiving 1.9.x from pip.
- **BREAKING (dependency floor)**: `duckdb>=2.0,<3`; `uv.lock` updated.
- Migrate DuckDB API uses:
  - `undatum/common/repack_duckdb.py` (`fetch_record_batch` / `to_arrow_reader` on a cursor)
    moves to `connection.sql(query).to_arrow_reader(batch_size)`;
  - audit every module that holds a connection (`cmds/api_app.py`, `mcp/`, `tools/`, `web/`,
    `tui/services.py`, ingesters) so that threads use their own `cursor()`;
  - check `write_csv`/`COPY` overwrite semantics against the atomic writer.
- Offline extensions:
  - honour `UNDATUM_DUCKDB_EXTENSION_DIR` (DuckDB `extension_directory`);
  - when a needed extension is missing and cannot be downloaded, fail with exit code 2 and a
    message naming the extension and the offline install command;
  - the Docker image and PyInstaller binaries ship the extensions undatum loads.

  Today undatum loads none; `refactor-duckdb-first-execution` may add `excel` and `encodings`.
- Apply `ruff --select UP --target-version py311 --fix` for safe modernisations.
- Documentation: README, AGENTS.md, `openspec/project.md`, installation page, CHANGELOG
  (**Breaking** section with the upgrade path).

## Impact
- Affected specs: `distribution`
- Affected code: `pyproject.toml`, `uv.lock`, `.github/workflows/*.yml`, `Dockerfile`,
  `packaging/`, `undatum/common/repack_duckdb.py`, `undatum/common/duckdb_config.py`, modules
  that share DuckDB connections, docs
- Depends on: nothing; `refactor-duckdb-first-execution` depends on this change
- Released as a minor version with a **Breaking** section, like the 3.9 removal in 1.8.0
