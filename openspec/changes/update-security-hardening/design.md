## Context
Agent tools are reachable through MCP (`undatum mcp serve`) and LangChain (`undatum/tools/`);
both call `undatum/tools/_core.py`, so sandboxing belongs there.

## Decisions
- **Sandbox root.** `ToolContext(root: Path)` is created once per server; `resolve_path()` applies
  `Path.resolve()` and rejects paths outside the root (including via symlinks). Default root is
  the working directory; `--root` overrides; `--allow-anywhere` exists for local trusted use and
  prints a warning.
- **DuckDB isolation.** Connection setup order: create the view over the sandboxed file, then
  `SET allowed_directories=[root]`, `SET enable_external_access=false`,
  `SET lock_configuration=true`. Statements are parsed with `duckdb`'s
  `extract_statements` and must be exactly one `SELECT` statement.
- **Rule expressions.** A small evaluator over Python `ast`: allowed nodes are `BoolOp`,
  `Compare`, `BinOp` (+ − × ÷ %), `UnaryOp` (not, −), `Name` (field lookup), `Constant`, and calls
  to `len`, `lower`, `upper`, `is_null`, `date`. Field names are resolved through a mapping, not
  string substitution.
- Alternatives: running agent SQL in a subprocess with seccomp (heavier, platform-specific);
  dropping `query_sql` (loses the most useful agent tool).

## Risks / Trade-offs
- Existing rule files using arbitrary Python fail → error message names the unsupported construct;
  CHANGELOG lists the supported grammar.
- `allowed_directories` requires DuckDB ≥ 1.3 → bound `duckdb>=1.3` in `pyproject.toml`.

## Migration Plan
Ship in v1.8 with CHANGELOG notes for the Data API key and rule grammar.
