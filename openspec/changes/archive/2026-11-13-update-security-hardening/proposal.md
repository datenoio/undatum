# Change: Harden Agent Tools, Rule Evaluation, Recipes, TLS and the Data API

## Why
- MCP/LangChain `query_sql` (`undatum/tools/_core.py:74-108`) runs arbitrary DuckDB SQL without
  confirmation and without path limits. A prompt-injected agent can read any file
  (`read_text('~/.ssh/id_rsa')`), write files (`COPY … TO`), install extensions or reach the
  network — bypassing the `confirm=True` gate that `dedup`, `mask` and `sample` enforce.
  Other tools accept any filesystem path as well.
- YAML cross-field rules are evaluated with `eval()` (`common/validation_rules.py:215`);
  `__builtins__: {}` is escapable through attribute chains, so an untrusted rules file can run
  code. Field-name substitution by string replacement (`:210`) breaks for names like `or`.
- `examples run` executes recipe commands with `shell=True` after variable substitution
  (`cmds/examples.py:320`).
- The Elasticsearch loader hardcodes `verify_certs=False` and hides the warning
  (`cmds/ingester/elastic.py:31-32`).
- The Data API accepts the key in the query string (`?api_key=`), compares it with `!=`
  (`cmds/api.py:514-515`) and runs uvicorn with `access_log=True` (`:908`), so keys land in logs;
  DuckDB queries run synchronously inside `async` handlers and block the event loop.

## What Changes
- Agent tools: a mandatory sandbox root (`undatum mcp serve --root DIR`, default: current
  directory); every path argument is resolved and must stay inside the root; DuckDB connections
  for tools set `enable_external_access=false` with `allowed_directories` limited to the root
  (DuckDB ≥ 1.3) and `lock_configuration=true`; `query_sql` accepts a single read-only `SELECT`
  /`WITH` statement.
- Validation rules: replace `eval()` with an AST-whitelist evaluator (comparisons, boolean ops,
  arithmetic, literals, field names, a fixed function set) or DuckDB expressions.
- Recipes: build an argv list with `shlex.split` and run with `shell=False`; quote substituted
  values; reject values containing shell metacharacters when a recipe declares a variable as a
  path.
- TLS: certificate verification on by default for Elasticsearch/OpenSearch; explicit
  `--insecure` flag with a visible warning; custom CA via `--ca-cert`.
- Data API: key only via `X-API-Key` header, constant-time comparison (`hmac.compare_digest`),
  never logged; queries run in a threadpool with a per-request timeout.

## Impact
- Affected specs: `data-security`, `data-validation`, `examples`, `data-api`
- Affected code: `undatum/tools/_core.py`, `undatum/mcp/server.py`, `undatum/cli/mcp_cli.py`,
  `undatum/common/validation_rules.py`, `undatum/cmds/examples.py`,
  `undatum/cmds/ingester/elastic.py`, `undatum/cmds/api.py`
- Behaviour change: `?api_key=` query parameter stops working (documented; header required)
