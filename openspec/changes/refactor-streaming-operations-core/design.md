## Context
CLI wrappers in `undatum/cli/` translate ~14 options per command into a dict; command classes in
`undatum/cmds/` read it with `get_option`. The SDK calls the same classes with temp files, and MCP
tools (`undatum/tools/_core.py`) partially re-implement logic. A shared, typed operation layer lets
CLI, SDK, MCP and pipelines become thin adapters (see `refactor-sdk-and-agent-adapters`).

## Goals / Non-Goals
- Goals: bounded memory for row-wise work; one write path for all formats; SQL pushdown where it
  is cheaper; testable pure functions; no behaviour change for users beyond fixes.
- Non-Goals: a general query planner; replacing DuckDB or iterabledata; distributed execution.

## Decisions
- **Operation contract**
  ```python
  @dataclass(frozen=True)
  class RenameConfig:
      mapping: dict[str, str] | None = None
      pattern: str | None = None
      replacement: str = ""

  class Rename(Operation[RenameConfig]):
      streaming = Streaming.ROW            # ROW | WINDOW | FULL
      def apply(self, rows: Iterable[dict], cfg: RenameConfig) -> Iterator[dict]: ...
      def to_sql(self, source: str, cfg: RenameConfig) -> str | None: ...
  ```
- **Registry**: `undatum.ops.REGISTRY[name] -> Operation`; adapters (CLI/SDK/MCP) are generated
  or hand-written against it; plugins can register `TransformPlugin` operations into it.
- **I/O**: `open_source(uri, format_in=None, **opts) -> RowSource` (with `.schema_hint`,
  `.duckdb_relation()` when available) and `open_sink(uri, format_out=None, **opts) -> RowSink`
  (`write_batch`, `close`, atomic rename on success, removal on failure).
- **Engine choice**: `auto` picks SQL when the source has a DuckDB relation and the operation
  provides `to_sql`; otherwise streaming Python. `--engine` forces either.
- **FULL operations** (`reverse`, `transpose`, non-SQL `sort`) use disk-backed buffers
  (`common/external_sort.py`, `common/disk_dedup.py` patterns) with a configurable memory cap.
- Alternatives considered: rewriting on pandas (not streaming), on polars (new heavy dependency,
  streaming API still evolving), all-DuckDB (loses 140+ iterabledata formats).

## Risks / Trade-offs
- Semantics differences between SQL and Python paths (null handling, regex flavour) → the contract
  suite runs every operation on both engines and compares outputs.
- Large refactor → migrate per command behind the same CLI; keep old class until its tests pass.

## Migration Plan
1. `io/` layer + `write_records` (already introduced by `fix-transform-output-writing`).
2. Registry and five pilot operations: `rename`, `fill`, `replace`, `search`, `head`.
3. Remaining row operations, then FULL operations with spill-to-disk.
4. Remove `DataWriter` (stdout handled by `open_sink`) and the converter monkeypatch.

## Resolved Questions
- Operation configs are frozen **dataclasses** (decision of 2026-10-07): no runtime cost, no
  pydantic dependency for the core; JSON schemas for agent tools are derived from the dataclass
  fields in `refactor-sdk-and-agent-adapters`.
- DuckDB pushdown runs with one thread and a 256 MB memory limit by default (overridable with
  `--duckdb-threads` / `--duckdb-memory`): row transforms are I/O bound, and per-thread buffers
  with insertion order preserved otherwise grow with the input.
- `to_sql` returns `None` whenever the SQL result could differ from the Python result (non-text
  columns for fill/replace/search, Python-only regex syntax, colliding renamed columns); COPY is
  used for CSV and Parquet only, and not for temporal columns, so both engines write the same text.
