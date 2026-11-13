## 1. Decision
- [x] 1.1 Approve Python 3.11+ and `duckdb>=2.0,<3` for the next minor release

## 2. Python 3.11+
- [x] 2.1 `requires-python`, classifiers, ruff `target-version`, mypy `python_version`
- [x] 2.2 CI matrices (`ci.yml` test matrix, base install, lowest dependencies, clean wheel smoke)
- [x] 2.3 `ruff --select UP --target-version py311 --fix`; re-run the mypy ratchet on 3.11
      (baseline 454 → 451)
- [x] 2.4 README, AGENTS.md, `openspec/project.md`, installation page

## 3. DuckDB 2.0
- [x] 3.1 `duckdb>=2.0,<3` in `pyproject.toml`; refresh `uv.lock` with the uv version that wrote it
- [x] 3.2 `common/repack_duckdb.py`: relation `to_arrow_reader(batch_size)` instead of cursor
      `to_arrow_reader` / `fetch_record_batch`; keep the record-batch comparison
- [x] 3.3 Audit connection sharing across threads (`api_app.py`, `mcp/`, `tools/`, `web/`,
      `tui/services.py`, ingesters); give each thread its own `cursor()`
- [x] 3.4 Check `COPY`/`write_csv` overwrite behaviour with `AtomicFileTarget`
- [x] 3.5 Run the engine contract suite (`tests/test_ops_contract.py`), the repack preservation
      suite and the memory budget tests on DuckDB 2.0

## 4. Offline extensions
- [x] 4.1 `UNDATUM_DUCKDB_EXTENSION_DIR` → `SET extension_directory` in `create_duckdb_connection`
- [x] 4.2 Missing extension without network: exit code 2, message names the extension and how to
      install it offline
- [x] 4.3 Preinstall loaded extensions in the Docker image and PyInstaller binaries (undatum
      loads no extension yet; revisit when `refactor-duckdb-first-execution` adds one)

## 5. Release
- [x] 5.1 CHANGELOG **Breaking** section with the upgrade path (pip on 3.10 resolves to 1.9.x)
- [x] 5.2 `openspec validate update-python-311-duckdb-2 --strict`
