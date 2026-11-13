# Change: Rule-File Validation Compiled to DuckDB SQL

## Why
`undatum validate --rules` and `undatum quality --rules` check every record in Python:
`ValidationRuleSet.validate_record()` runs each rule's checks in order, and `unique` and
`references` keep value stores that spill to SQLite. On large CSV files this is the slowest
part of validation. The simple checks (required, data type, references, unique, numeric range,
length, enum, pattern) can run as one DuckDB query that returns the same violations. This is
item 16 of the October 2026 engine review (`analysis/2026-10-28-undatum-engines-and-competitors.md`).

## What Changes
- **`undatum.validate.sql`:** compiles a rule set into one DuckDB query over the input's
  records, numbered in input order. Each rule becomes a `CASE` that returns the message of its
  first failing check, in the order and with the text of the Python rule.
  - `unique`: a window over the values that passed the earlier checks gives the first row.
  - `references`: a semi-join on the reference file's values.
  - `pattern`: translated to RE2 (anchored at the start like `re.match`; `\d` as `\p{Nd}`; `$`
    also before a final newline). Patterns using `\w`, `\s`, `\b` or their negations, or that RE2
    cannot compile, keep the Python engine.
- **Python numbers:** numbers follow Python's `float()` and `int()` grammar (underscores,
  `inf`, `nan`, surrounding whitespace). NaN is not compared in range checks: DuckDB orders NaN
  above every number. A value that looks numeric but uses characters outside ASCII (other
  digits or spaces) makes the query hand the file to the Python engine, since only Python reads
  it.
- **When it applies:** CSV and TSV input that DuckDB reads, field rules without `format` or
  `custom`, and a `--filter` that translates to SQL. Otherwise the Python engine checks the
  records as before.
- **Engine option:** `validate` gains `--engine auto|duckdb|python` (default `auto`).
  `quality --rules` uses the same path.
- **Not in this change:** structural errors through `store_rejects`, `format`/`custom` rules
  and cross-field conditions stay in Python.

## Impact
- Affected specs: `data-processing`.
- Affected code: `undatum/validate/sql.py` (new), `undatum/cmds/validator.py`,
  `undatum/cmds/quality.py`, `undatum/cli/commands/quality.py`, tests and documentation.
