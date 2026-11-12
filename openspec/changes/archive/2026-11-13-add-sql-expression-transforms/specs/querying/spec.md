## ADDED Requirements

### Requirement: Row Filter Expressions
Commands that read records SHALL accept `--where` with a SQL boolean expression and SHALL output
only rows for which the expression is true, for every supported input format.

#### Scenario: Filter JSON Lines with SQL
- **WHEN** user runs `undatum select data.jsonl --where "amount > 100 AND city = 'Berlin'" -o out.csv`
- **THEN** `out.csv` contains only matching rows

#### Scenario: Unknown column
- **WHEN** user runs `undatum select data.csv --where "amout > 100"`
- **THEN** the command exits with code 1 and suggests `amount`

### Requirement: Computed Columns
`select` and `convert` SHALL accept repeatable `--add "name = expression"` options that append
columns computed from SQL expressions.

#### Scenario: Add total column
- **WHEN** user runs `undatum convert orders.csv orders.parquet --add "total = price * qty"`
- **THEN** each output row has a `total` column equal to `price * qty`
