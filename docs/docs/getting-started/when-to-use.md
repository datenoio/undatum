---
title: "When to use undatum"
description: "undatum vs miller, DuckDB, and csvkit"
---
# When to use undatum vs miller vs DuckDB vs csvkit

Evaluators often ask which CLI to reach for. Short answer: **undatum is a multiformat
record-stream Swiss army knife** with validation, packaging, and agent/MCP hooks.
Use the others when you want their specialized strengths.

| Need | Prefer |
|------|--------|
| Convert / validate / package across CSV, JSONL, BSON, Excel, Parquet, XML, … | **undatum** |
| Millisecond CSV/TSV reshaping, joins, and awk-like pipelines | **miller** |
| Ad-hoc SQL analytics with spill-to-disk on Parquet/CSV | **DuckDB** CLI (also available inside undatum via `sql` / engine auto) |
| Classic CSV-only toolkit (csvcut, csvstat) familiar to many Python users | **csvkit** |
| Agent/MCP tooling over datasets | **undatum** (`mcp serve`, `undatum.tools`) |
| Frictionless / open-data publishing helpers | **undatum** (`package`, `validate`, Russian INN/OGRN rules) |

## undatum strengths

- Breadth: 140+ formats via iterabledata (tabular, geospatial, lakehouse, scientific; inspect with `undatum formats list --capabilities`)
- Streaming-first CLI with `--low-memory` for multi-GB converts/sorts/dedups
- Validation, masking, Frictionless packaging, AI doc helpers
- Agent-native surface (MCP + JSON tools)

## When another tool wins

- **miller**: pure delimited text, tiny binary, extreme pipe composition
- **DuckDB**: you already think in SQL and live in Parquet warehouses
- **csvkit**: teaching/simple CSV-only scripts with zero learning curve beyond csv*

## Related docs

- [Quickstarts](/getting-started/quick-start)
- [Coming from csvkit](/getting-started/from-csvkit) and [from qsv](/getting-started/from-qsv)
- [Cheat sheet](/getting-started/cheat-sheet)
- [Format support](/formats/)
- [Performance](/getting-started/performance)
