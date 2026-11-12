## 1. Lazy loading
- [x] 1.0 Split `undatum/cli/data_commands.py` (3 692 lines) into one module per command under
      `undatum/cli/commands/` so each command can be imported on demand
      (done as one module per area — convert, explore, describe, records, fields, combine,
      quality, query — with shared option aliases in `undatum/cli/options.py`; `--help` output
      is unchanged; in-function imports already keep startup within budget)
- [x] 1.1 Introduce a lazy group (command name → import path) for top-level commands and sub-apps
- [x] 1.2 Move heavy imports inside command bodies; remove module-level pandas/duckdb imports from
      modules imported at startup
- [x] 1.3 Lazy plugin discovery and import

## 2. Logging
- [x] 2.1 Replace `logging.basicConfig(level=INFO)` with an `undatum` logger at WARNING
- [x] 2.2 Replace root-logger calls (`logging.info`) with module loggers
- [x] 2.3 Add global `-v/-vv/-q`; map per-command `--verbose` to the same setting

## 3. Guardrails
- [x] 3.1 Test: `python -X importtime -c "import undatum.core"` contains no pandas/duckdb/pyarrow
- [x] 3.2 Test: `undatum --version` wall time ≤ 0.3 s on CI (median of 5 runs)
- [x] 3.3 Test: a successful `undatum count data.csv` writes nothing to stderr
