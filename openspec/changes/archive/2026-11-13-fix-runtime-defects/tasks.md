## 1. Fixes
- [x] 1.1 Fix unbound variables in `sampler.py`, `slicer.py`, `postgres.py`, `mysql_backend.py`,
      `schema_utils.py`; malformed input raises `ValidationError`
- [x] 1.2 Fix B023 closures in `cmds/api.py` (`max_limit`, `default_limit` bound per resource)
- [x] 1.3 `elastic.py`: `request_timeout=timeout`; bound `elasticsearch>=8,<10` in `pyproject.toml`
- [x] 1.4 SDK: register temp files, delete after consumption, add `close()`, `__enter__`/`__exit__`
      and an `atexit` fallback

## 2. Tests
- [x] 2.1 One regression test per unbound-variable site
- [x] 2.2 Data API test with two resources having different `max_limit` values
- [x] 2.3 Elasticsearch ingester test that constructs the client with the installed major version
- [x] 2.4 SDK test asserting no files remain in the temp directory after a 3-step chain
