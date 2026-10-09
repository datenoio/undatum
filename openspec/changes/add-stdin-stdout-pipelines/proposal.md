# Change: Support Unix Pipelines (stdin input, input-shaped stdout)

## Why
Commands print results to stdout but cannot read from stdin: `cat data.csv | undatum head -`
fails with "File not found: '-'". Output on stdout is always JSONL, even for CSV input
(`undatum head data.csv` prints JSON lines). So undatum commands cannot be chained, unlike
qsv, xsv or Miller where `… | sort | dedup | head` is the basic workflow.

## What Changes
- An input path of `-` (or an omitted input for single-input commands) reads from stdin.
- Input format on stdin comes from `--format-in` or from sniffing the first bytes (JSON, JSON
  Lines, CSV/TSV); compressed stdin is detected by magic bytes.
- Stdout uses the input's text format (CSV in → CSV out, JSONL in → JSONL out); `--format-out`
  overrides. Non-text sources default to JSONL on stdout.
- Binary formats (Parquet, XLSX, ORC, Avro) are written to stdout only with explicit
  `--format-out` and never to a terminal.
- In pipes: no progress bars, `BrokenPipeError` exits quietly with code 0.
- Upstream: reading from file objects/stdin in iterabledata (see `refactor-streaming-operations-core`).

## Impact
- Affected specs: `cli-conventions`
- Affected code: input/output helpers in `undatum/common/`, all row-input commands,
  `docs/docs/getting-started/basic-usage.md`
- Behaviour change: stdout of CSV-input commands becomes CSV instead of JSONL (documented in
  CHANGELOG; `--format-out jsonl` restores the old output)
