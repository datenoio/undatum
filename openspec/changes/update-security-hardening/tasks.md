## 1. Agent tools
- [x] 1.1 Add `ToolContext` with sandbox root and `resolve_path()`; apply to every tool argument
- [x] 1.2 `undatum mcp serve --root DIR` (default cwd) and `--allow-anywhere`
- [x] 1.3 DuckDB isolation settings for tool connections; single read-only SELECT check
- [x] 1.4 Tests: path traversal, symlink escape, `COPY … TO`, `read_text` outside root, `INSTALL`

## 2. Rules
- [x] 2.1 Implement the AST-whitelist evaluator and replace `eval()`
- [x] 2.2 Resolve field names by mapping; test field names `or`, `and`, `class`
- [x] 2.3 Test escape attempts (`().__class__.__bases__`) are rejected

## 3. Recipes
- [x] 3.1 `shlex.split` + `shell=False` in `examples run`; quote substituted values
- [x] 3.2 Test that a variable value `x; rm -rf ~` is passed as a literal argument

## 4. TLS and Data API
- [x] 4.1 Elasticsearch: verify certificates by default; `--insecure`, `--ca-cert`
- [x] 4.2 Data API: header-only key, `hmac.compare_digest`, redact key from logs
- [x] 4.3 Data API: execute queries in a threadpool with a configurable timeout
- [x] 4.4 Bound `duckdb>=1.3` and document security settings in `docs/docs/integrations/mcp.md`
