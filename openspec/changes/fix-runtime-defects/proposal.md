# Change: Fix Runtime Defects Found by Static Analysis and Review

## Why
The 2026-09-18 and 2026-10-07 reviews confirmed defects on reachable paths that are still present
on `master`:
- unbound variables (pylint E0606): `cmds/sampler.py:97`, `cmds/slicer.py:76,148,152`,
  `cmds/ingester/postgres.py:112` and `cmds/ingester/mysql_backend.py:100` (URI without `@`),
  `common/schema_utils.py:313`;
- loop-variable closure (ruff B023) in `cmds/api.py:703-725`: every Data API route uses the
  pagination limits of the last configured resource;
- `Elasticsearch(timeout=...)` in `cmds/ingester/elastic.py:28` is rejected by
  elasticsearch-py 8.x/9.x (the dev venv has 9.4.1);
- the SDK creates a temporary JSONL file per chained step (`sdk/dataset.py`,
  `_get_temp_output`) and never deletes it, leaving a full copy of the data per step.

## What Changes
- Initialise or guard each unbound variable and raise `ValidationError` for malformed inputs.
- Bind loop values as default arguments in the generated API handlers.
- Use `request_timeout` for the Elasticsearch client and bound `elasticsearch>=8,<10`.
- Track SDK temporary files and delete them when the next step has consumed them, when the
  `Dataset` is closed, or at interpreter exit; make `Dataset` a context manager.
- Add a regression test for each defect.

## Impact
- Affected specs: `data-api`, `database-integration`, `sdk`, `error-handling`
- Affected code: modules listed above, `pyproject.toml`
- Related: review defects #4, #5, #6, #9
