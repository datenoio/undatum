## ADDED Requirements

### Requirement: Typed Excel Input
undatum SHALL read local xlsx, xlsm, xls, xlsb and ods files with fastexcel into typed values:
numbers (integers when every value of a column is whole), dates or datetimes, booleans, text, and
null for empty cells; formula cells SHALL give their cached results. The Python engine and DuckDB
SHALL read the same values from one Arrow table per sheet.

#### Scenario: Numbers and empty cells
- **WHEN** a user runs `undatum head data.xlsx -O jsonl` on a sheet with a column of whole numbers
  and an empty cell
- **THEN** the numbers are JSON integers and the empty cell is `null`

#### Scenario: Engines agree
- **WHEN** a user runs `undatum frequency data.xlsx -f region` with `--engine python` and with
  `--engine duckdb`
- **THEN** both print the same counts

#### Scenario: Named sheet
- **WHEN** a user runs `undatum count data.xlsx --sheet Sales`
- **THEN** the records of the sheet `Sales` are counted
