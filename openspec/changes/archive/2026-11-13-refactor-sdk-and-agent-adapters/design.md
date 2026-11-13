## Decisions
- **Plan model**: `Dataset` holds `source: SourceSpec` and `steps: tuple[OperationCall, ...]`;
  transform methods return a new `Dataset` with one more step (immutable, cheap).
- **Execution**: if the source exposes a DuckDB relation and every step has `to_sql`, compose SQL;
  otherwise chain `apply()` generators. FULL operations spill to disk inside the operation, not
  between steps.
- **Typing**: records stay Python objects across steps; only sinks serialize.
- **Tools**: a generator walks `ops.REGISTRY` and produces MCP tools with JSON Schema from the
  config model; read-only operations become query tools, writing operations require `output` and
  `confirm=True`.
- Backward compatibility: existing method names and signatures keep working; `Dataset(source=...)`
  still accepted.

## Risks / Trade-offs
- Lazy evaluation changes when errors surface (at execution rather than at method call) →
  validate configs eagerly at method call, run data-dependent checks at execution.
