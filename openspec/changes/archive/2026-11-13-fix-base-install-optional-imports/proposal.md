# Change: Fix Clean Install Broken by Optional-Extra Imports

## Why
`pip install undatum==1.7.0` (also `pipx` and `uv tool install`) produces a CLI that fails on
`undatum --version` with `ModuleNotFoundError: No module named 'starlette'`.
`undatum/cmds/api.py:19` imports `starlette.requests.Request` at module level, and
`undatum/core.py` imports `undatum/cli/api_cli.py` → `undatum/cmds/api.py` on every invocation.
`starlette` belongs to the optional `api` extra. The test job installs `.[api]`, so the suite never
sees the failure. This is the third missing-dependency release after #19 (`xmltodict`) and #37
(`chardet`).

## What Changes
- Move `starlette`/`fastapi`/`uvicorn` imports in `undatum/cmds/api.py` into the functions that
  need them (types under `TYPE_CHECKING`).
- Audit every module reachable from `undatum.core` for top-level imports of packages that only
  ship in extras (`api`, `web`, `tui`, `mcp`, `plot`, `extract`, `s3`/`gcs`/`azure`/`cloud`,
  database drivers, `polars`, `dask`, `frictionless`) and make them lazy.
- Raise `DependencyError` (exit code 2) with the exact `pip install "undatum[<extra>]"` hint when
  a command needs a missing extra.
- Add a test that imports every module reachable from `undatum.core` and runs `undatum --version`
  in an environment without any extras.
- Release v1.7.1; decide whether to yank 1.7.0 on PyPI with a reason that points to 1.7.1.

## Impact
- Affected specs: `distribution`
- Affected code: `undatum/cmds/api.py`, `undatum/cli/*.py`, `undatum/core.py`, `tests/`
- Related: issues #19, #37; review defect #0
