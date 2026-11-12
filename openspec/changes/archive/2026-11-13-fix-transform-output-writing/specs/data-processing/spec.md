## ADDED Requirements

### Requirement: Transform Output Format Fidelity
Every command that writes records to `--output` SHALL write them in the format implied by the
output path (or `--format-out`) for every format that iterabledata can write, and SHALL fail with a
non-zero exit code instead of creating an empty file when the format cannot be written.

#### Scenario: Parquet output from a row transform
- **WHEN** user runs `undatum rename data.csv --map "a:x" --output out.parquet`
- **THEN** `out.parquet` contains every input row with field `x` instead of `a`
- **AND** the exit code is 0

#### Scenario: Unsupported output format
- **WHEN** user runs `undatum fill data.csv --value 0 --output out.unknownext`
- **THEN** the command exits with code 1 and a "Unsupported file format" message
- **AND** `out.unknownext` does not exist

#### Scenario: Compressed output
- **WHEN** user runs `undatum head data.jsonl --limit 20 --output out.csv.gz`
- **THEN** `out.csv.gz` is a gzip-compressed CSV with 20 data rows

## MODIFIED Requirements

### Requirement: Reverse Command
The system SHALL provide a `reverse` command that reverses the order of rows in a data file.

#### Scenario: Reverse rows in CSV file
- **WHEN** user runs `undatum reverse data.csv --output output.csv`
- **THEN** the system writes all rows in reverse order to output file

#### Scenario: Reverse rows with streaming
- **WHEN** user runs `undatum reverse large_file.jsonl --output output.jsonl`
- **THEN** the system processes rows efficiently without loading entire file into memory

### Requirement: Enum Command
The system SHALL provide an `enum` command that adds sequential numbers, UUIDs, or constant values to records.

#### Scenario: Add row numbers
- **WHEN** user runs `undatum enum data.csv --field row_id --output output.csv`
- **THEN** the system adds a `row_id` field with sequential numbers starting from 1

#### Scenario: Add UUIDs
- **WHEN** user runs `undatum enum data.jsonl --field id --type uuid --output output.jsonl`
- **THEN** the system adds an `id` field with unique UUIDs for each row

#### Scenario: Add constant value
- **WHEN** user runs `undatum enum data.csv --field status --value "active" --output output.csv`
- **THEN** the system adds a `status` field with the constant value "active" for all rows

#### Scenario: Add row numbers with custom start
- **WHEN** user runs `undatum enum data.csv --field num --start 100 --output output.csv`
- **THEN** the system adds row numbers starting from 100

### Requirement: Head Command
The system SHALL provide a `head` command that extracts the first N rows from a data file.

#### Scenario: Extract first 10 rows
- **WHEN** user runs `undatum head data.csv --limit 10`
- **THEN** the system outputs the first 10 rows to stdout

#### Scenario: Extract first rows to file
- **WHEN** user runs `undatum head data.jsonl --limit 20 --output output.jsonl`
- **THEN** the system writes first 20 rows to output file

### Requirement: Tail Command
The system SHALL provide a `tail` command that extracts the last N rows from a data file.

#### Scenario: Extract last 10 rows
- **WHEN** user runs `undatum tail data.csv --limit 10`
- **THEN** the system outputs the last 10 rows to stdout

#### Scenario: Extract last rows with buffering
- **WHEN** user runs `undatum tail large_file.jsonl --limit 50 --output output.jsonl`
- **THEN** the system efficiently extracts last 50 rows without loading entire file

### Requirement: Fixlengths Command
The system SHALL provide a `fixlengths` command that ensures all rows have the same number of fields.

#### Scenario: Pad rows with empty string
- **WHEN** user runs `undatum fixlengths data.csv --strategy pad --value "" --output output.csv`
- **THEN** the system pads shorter rows with empty strings to match the maximum field count

#### Scenario: Truncate rows
- **WHEN** user runs `undatum fixlengths data.csv --strategy truncate --output output.csv`
- **THEN** the system truncates longer rows to match the minimum field count

#### Scenario: Pad rows with custom value
- **WHEN** user runs `undatum fixlengths data.jsonl --strategy pad --value "N/A" --output output.jsonl`
- **THEN** the system pads shorter rows with "N/A" value

### Requirement: Sort Command
The system SHALL provide a `sort` command that sorts rows by one or more columns.

#### Scenario: Sort by single column ascending
- **WHEN** user runs `undatum sort data.csv --by name --output output.csv`
- **THEN** the system sorts rows by the `name` column in ascending order

#### Scenario: Sort by multiple columns
- **WHEN** user runs `undatum sort data.jsonl --by name,age --output output.jsonl`
- **THEN** the system sorts rows first by `name`, then by `age`

#### Scenario: Sort descending
- **WHEN** user runs `undatum sort data.csv --by date --desc --output output.csv`
- **THEN** the system sorts rows by `date` in descending order

#### Scenario: Sort large file with external merge
- **WHEN** user runs `undatum sort large_file.csv --by id --output output.csv`
- **THEN** the system uses external merge sort to handle the file efficiently

#### Scenario: Numeric sort
- **WHEN** user runs `undatum sort data.csv --by price --numeric --output output.csv`
- **THEN** the system sorts `price` as numbers rather than strings

### Requirement: Sample Command
The system SHALL provide a `sample` command that randomly selects rows from a data file.

#### Scenario: Sample fixed number of rows
- **WHEN** user runs `undatum sample data.csv --limit 1000 --output output.csv`
- **THEN** the system randomly selects 1000 rows using reservoir sampling

#### Scenario: Sample by percentage
- **WHEN** user runs `undatum sample data.jsonl --percent 10 --output output.jsonl`
- **THEN** the system randomly selects 10% of rows

#### Scenario: Sample without loading entire file
- **WHEN** user runs `undatum sample large_file.csv --limit 100 --output output.csv`
- **THEN** the system uses reservoir sampling algorithm that doesn't require loading all data

### Requirement: Dedup Command
The system SHALL provide a `dedup` command that removes duplicate rows.

#### Scenario: Deduplicate by all fields
- **WHEN** user runs `undatum dedup data.csv --output output.csv`
- **THEN** the system removes rows that are identical in all fields

#### Scenario: Deduplicate by key fields
- **WHEN** user runs `undatum dedup data.jsonl --key-fields email --output output.jsonl`
- **THEN** the system removes rows with duplicate `email` values, keeping the first occurrence

#### Scenario: Keep last duplicate
- **WHEN** user runs `undatum dedup data.csv --key-fields id --keep last --output output.csv`
- **THEN** the system removes duplicates keeping the last occurrence

#### Scenario: Deduplicate large file externally
- **WHEN** user runs `undatum dedup large_file.jsonl --output output.jsonl`
- **THEN** the system uses external approach for memory efficiency

### Requirement: Fill Command
The system SHALL provide a `fill` command that fills empty or null values.

#### Scenario: Fill with constant value
- **WHEN** user runs `undatum fill data.csv --fields name,email --value "N/A" --output output.csv`
- **THEN** the system fills empty values in `name` and `email` fields with "N/A"

#### Scenario: Forward fill
- **WHEN** user runs `undatum fill data.jsonl --fields status --strategy forward --output output.jsonl`
- **THEN** the system fills empty values with the previous non-empty value

#### Scenario: Backward fill
- **WHEN** user runs `undatum fill data.csv --fields category --strategy backward --output output.csv`
- **THEN** the system fills empty values with the next non-empty value

### Requirement: Rename Command
The system SHALL provide a `rename` command that renames fields.

#### Scenario: Rename by exact mapping
- **WHEN** user runs `undatum rename data.csv --map "old_name:new_name,old2:new2" --output output.csv`
- **THEN** the system renames `old_name` to `new_name` and `old2` to `new2`

#### Scenario: Rename using regex
- **WHEN** user runs `undatum rename data.jsonl --pattern "^prefix_" --replacement "" --output output.jsonl`
- **THEN** the system removes "prefix_" from the beginning of all field names

### Requirement: Explode Command
The system SHALL provide an `explode` command that splits a column by separator into multiple rows.

#### Scenario: Explode comma-separated values
- **WHEN** user runs `undatum explode data.csv --field tags --separator "," --output output.csv`
- **THEN** the system creates one row per tag value, duplicating other fields

#### Scenario: Explode pipe-separated values
- **WHEN** user runs `undatum explode data.jsonl --field categories --separator "|" --output output.jsonl`
- **THEN** the system splits `categories` by "|" and creates multiple rows

### Requirement: Replace Command
The system SHALL provide a `replace` command that performs string replacement in fields.

#### Scenario: Simple string replacement
- **WHEN** user runs `undatum replace data.csv --field name --pattern "Mr\." --replacement "Mr" --output output.csv`
- **THEN** the system replaces "Mr." with "Mr" in the `name` field

#### Scenario: Regex replacement
- **WHEN** user runs `undatum replace data.jsonl --field email --pattern "@old.com" --replacement "@new.com" --regex --output output.jsonl`
- **THEN** the system replaces email domain using regex pattern

#### Scenario: Global replacement
- **WHEN** user runs `undatum replace data.csv --field text --pattern "old" --replacement "new" --global-replace --output output.csv`
- **THEN** the system replaces all occurrences of "old" with "new" in the `text` field

### Requirement: Cat Command
The system SHALL provide a `cat` command that concatenates files.

#### Scenario: Concatenate files by rows
- **WHEN** user runs `undatum cat file1.csv file2.csv --mode rows --output output.csv`
- **THEN** the system appends rows from file2 to file1, handling headers appropriately

#### Scenario: Concatenate files by columns
- **WHEN** user runs `undatum cat file1.csv file2.csv --mode columns --output output.csv`
- **THEN** the system combines files side-by-side, matching rows by position
