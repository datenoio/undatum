# data-processing Specification

## Purpose
Infer and export schemas (`schema` / `schema_bulk`) in JSON Schema, YAML, Frictionless, and Cerberus formats.
## Requirements
### Requirement: JSON Schema Export
The system SHALL support exporting schemas in JSON Schema format (W3C/IETF standard).

#### Scenario: Export schema as JSON Schema
- **WHEN** user runs `undatum schema data.csv --format jsonschema`
- **THEN** the system outputs a valid JSON Schema document following JSON Schema draft-07 specification

#### Scenario: JSON Schema includes type information
- **WHEN** user runs `undatum schema data.jsonl --format jsonschema`
- **THEN** the output includes proper type mappings (string, integer, number, boolean, object, array)

#### Scenario: JSON Schema handles nested structures
- **WHEN** user runs `undatum schema nested_data.jsonl --format jsonschema`
- **THEN** the output includes nested object definitions for STRUCT types

#### Scenario: JSON Schema includes field descriptions
- **WHEN** user runs `undatum schema data.csv --format jsonschema --autodoc`
- **THEN** the output includes description fields for each property

### Requirement: Avro Schema Export
The system SHALL support exporting schemas in Avro schema format.

#### Scenario: Export schema as Avro schema
- **WHEN** user runs `undatum schema data.jsonl --format avro`
- **THEN** the system outputs a valid Avro schema JSON document

#### Scenario: Avro schema includes proper type mappings
- **WHEN** user runs `undatum schema data.csv --format avro`
- **THEN** the output maps data types to Avro types (string, int, long, double, boolean, etc.)

#### Scenario: Avro schema handles nested records
- **WHEN** user runs `undatum schema nested_data.jsonl --format avro`
- **THEN** the output includes nested record definitions for STRUCT types

### Requirement: Parquet Schema Export
The system SHALL support exporting schemas in Parquet schema format.

#### Scenario: Export schema as Parquet schema
- **WHEN** user runs `undatum schema data.parquet --format parquet`
- **THEN** the system outputs Parquet schema information

#### Scenario: Parquet schema from other formats
- **WHEN** user runs `undatum schema data.csv --format parquet`
- **THEN** the system converts the CSV schema to Parquet schema format

### Requirement: Schema Extraction Command
The system SHALL provide a unified `schema` command that supports multiple schema output formats through a `--format` parameter.

#### Scenario: Extract schema in Cerberus format
- **WHEN** user runs `undatum schema data.jsonl --format cerberus`
- **THEN** the system outputs Cerberus validation schema in JSON format

#### Scenario: Extract schema in JSON Schema format
- **WHEN** user runs `undatum schema data.csv --format jsonschema`
- **THEN** the system outputs JSON Schema (W3C/IETF standard) format

#### Scenario: Extract schema in Avro format
- **WHEN** user runs `undatum schema data.jsonl --format avro`
- **THEN** the system outputs Avro schema format

#### Scenario: Extract schema in Parquet format
- **WHEN** user runs `undatum schema data.parquet --format parquet`
- **THEN** the system outputs Parquet schema format

#### Scenario: Extract schema in default YAML format
- **WHEN** user runs `undatum schema data.csv` (without --format)
- **THEN** the system outputs schema in YAML format (default)

#### Scenario: Bulk extraction with format selection
- **WHEN** user runs `undatum schema_bulk data/ --format jsonschema --output schemas/`
- **THEN** the system extracts schemas in JSON Schema format for all files

### Requirement: Scheme Command Deprecation
The legacy `scheme` command SHALL be deprecated in favor of `undatum schema --format cerberus` while continuing to work with a deprecation warning during the transition period.

#### Scenario: Deprecated scheme command invocation
- **WHEN** user runs `undatum scheme data.jsonl`
- **THEN** the system shows a deprecation warning recommending `undatum schema --format cerberus`
- **AND** still produces the Cerberus schema output for backward compatibility

### Requirement: Count Command
The system SHALL provide a `count` command that counts the number of rows in a data file.

#### Scenario: Count rows in CSV file
- **WHEN** user runs `undatum count data.csv`
- **THEN** the system outputs the total number of data rows (excluding header if present)

#### Scenario: Count rows with DuckDB optimization
- **WHEN** user runs `undatum count data.csv` on a supported format
- **THEN** the system uses DuckDB engine for instant counting when available

#### Scenario: Count rows in JSONL file
- **WHEN** user runs `undatum count data.jsonl`
- **THEN** the system counts and outputs the number of JSON objects (one per line)

### Requirement: Table Command
The system SHALL provide a `table` command that displays data in a formatted, aligned table for inspection.

#### Scenario: Display table with default limit
- **WHEN** user runs `undatum table data.csv`
- **THEN** the system displays first 20 rows in a formatted table with aligned columns

#### Scenario: Display table with custom limit
- **WHEN** user runs `undatum table data.csv --limit 50`
- **THEN** the system displays first 50 rows in formatted table

#### Scenario: Display table with selected fields
- **WHEN** user runs `undatum table data.jsonl --fields name,email,status`
- **THEN** the system displays only the specified fields in the table

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

### Requirement: Search Command
The system SHALL provide a `search` command that filters rows using regex patterns.

#### Scenario: Search across all fields
- **WHEN** user runs `undatum search data.csv --pattern "error|warning"`
- **THEN** the system outputs rows where any field matches the pattern

#### Scenario: Search in specific fields
- **WHEN** user runs `undatum search data.jsonl --pattern "^[0-9]+$" --fields id,code`
- **THEN** the system outputs rows where `id` or `code` fields match the pattern

#### Scenario: Case-insensitive search
- **WHEN** user runs `undatum search data.csv --pattern "ERROR" --ignore-case`
- **THEN** the system matches regardless of case

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

### Requirement: Plot Command
The system SHALL provide a `plot` command that writes matplotlib charts from
tabular files. Bar charts SHALL support filtering and aggregation.

#### Scenario: Filter then plot
- **WHEN** user runs `undatum plot data.csv --field city --type bar --filter 'age >= 30' --output cities.png`
- **THEN** the system plots only matching rows and writes a PNG file

#### Scenario: Aggregate bar chart
- **WHEN** user runs `undatum plot data.csv --field city --type bar --aggregate sum --value-field amount --output totals.png`
- **THEN** the system groups by city, sums `amount`, and writes a PNG file

### Requirement: Stats profiling reports
The system SHALL emit dataset profiles as a terminal table by default, and as
JSON, HTML, or Markdown when requested via `--format-out` or inferred from the
output file extension.

#### Scenario: HTML profile report
- **WHEN** user runs `undatum stats data.csv --format-out html --output profile.html`
- **THEN** the system writes an HTML document with a field-statistics table

#### Scenario: Markdown inferred from extension
- **WHEN** user runs `undatum stats data.csv --output profile.md`
- **THEN** the system writes a Markdown profiling report

### Requirement: JSON analysis output
The system SHALL emit JSON for `headers`, `frequency`, `uniq`, `sniff`, and
`analyze` when `--format-out json` (or `--outtype json` for analyze) is set or
the output path ends in `.json`.

#### Scenario: Headers as JSON
- **WHEN** user runs `undatum headers data.csv --format-out json`
- **THEN** the system prints a JSON object with a `fields` array

#### Scenario: Frequency as JSON
- **WHEN** user runs `undatum frequency --fields city --format-out json data.csv`
- **THEN** the system prints a JSON array of `{field, count}` records

#### Scenario: Analyze as Markdown
- **WHEN** user runs `undatum analyze data.csv --output report.md`
- **THEN** the system writes a Markdown analysis report with field tables

### Requirement: CLI defaults configuration
The system SHALL load command defaults from `undatum.yaml` in the current
directory, `~/.undatum/config.yaml`, and `UNDATUM_*` environment variables.
Explicit CLI flags SHALL override config. Project file SHALL override the home
file. Config files SHALL override environment variables.

#### Scenario: Engine default from project file
- **WHEN** `undatum.yaml` contains `defaults.engine: python` and the user omits `--engine`
- **THEN** commands that select an engine use the Python/iterable engine

#### Scenario: Inspect resolved defaults
- **WHEN** user runs `undatum config show`
- **THEN** the system prints the merged defaults and which config files were found

### Requirement: Manual page
The system SHALL ship an `undatum(1)` manual page that lists commands, config
files, environment variables, and exit codes.

#### Scenario: Man page is generated from the CLI
- **WHEN** a maintainer runs `make man`
- **THEN** `man/undatum.1` is regenerated from the current Typer command tree

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

### Requirement: Partitioned Output
`split` and `convert` SHALL write partitioned output by the values of chosen fields, using
Hive-style `field=value` directories when requested, in any writable format, with a bounded number
of simultaneously open files.

#### Scenario: Hive-partitioned Parquet from convert
- **WHEN** user runs `undatum convert sales.csv out/ --partition-by year,month --format-out parquet`
- **THEN** files are written under `out/year=<y>/month=<m>/`
- **AND** reading `out/**/*.parquet` with DuckDB returns all input rows

#### Scenario: Hive layout for split
- **WHEN** user runs `undatum split data.csv --fields region --hive --dirname parts/`
- **THEN** each distinct `region` value gets a directory `parts/region=<value>/`

#### Scenario: High-cardinality key
- **WHEN** the partition key has more distinct values than `--max-open-files`
- **THEN** the command still completes and every row is written to its partition

### Requirement: Conversion Through DuckDB for Native Formats
With `--engine auto`, `convert` SHALL write the output with DuckDB `COPY` when DuckDB reads the
input and writes the output format natively (CSV/TSV, JSON, JSON Lines, Parquet; plain, gzip or
zstd), and the records SHALL be identical to those of the Python engine.

#### Scenario: CSV to JSON Lines
- **WHEN** a user runs `undatum convert data.csv data.jsonl`
- **THEN** DuckDB writes `data.jsonl`
- **AND** every record equals the record `--engine python` writes, including original CSV text
  and empty values

#### Scenario: Format DuckDB cannot write
- **WHEN** the output format is not written natively by DuckDB (for example XLSX)
- **THEN** the records are written by the iterabledata writer from DuckDB's result batches or
  the Python engine

#### Scenario: Column types DuckDB writes differently
- **WHEN** the result has a column whose values DuckDB `COPY` writes differently from the Python
  writer (for example timestamps in CSV, UUIDs in Parquet)
- **THEN** the records are written by the Python writer
- **AND** dates and the other types `COPY` writes identically keep using `COPY`, with CSV lines
  ending in CRLF as the Python writer ends them

### Requirement: Workload-Based DuckDB Settings
Every DuckDB query SHALL run on a connection made by the shared connection factory. Row-wise and
window operations SHALL use one thread and a bounded memory limit. Aggregations and sorts SHALL
use all CPU cores and DuckDB's default memory limit. `--duckdb-threads`, `--duckdb-memory` and
`--duckdb-temp-dir` SHALL override these defaults for every command.

#### Scenario: Aggregation uses all cores
- **WHEN** a user runs `undatum frequency data.csv -f city` on a machine with 8 cores
- **THEN** the DuckDB query runs with 8 threads

#### Scenario: Row-wise transform stays bounded
- **WHEN** a user runs `undatum rename` on a 1M-row CSV
- **THEN** the DuckDB query runs with one thread and the default 256 MB limit
- **AND** the memory budget of row-wise transforms holds

#### Scenario: Override applies everywhere
- **WHEN** a user passes `--duckdb-memory 2GB` to `stats`, `quality` or `schema-drift`
- **THEN** the DuckDB connection of that command uses a 2 GB memory limit

### Requirement: Profiling in a Few Scans
For DuckDB-readable inputs, `stats` SHALL compute the counts, missing values, lengths and numeric
distributions of all fields in one scan of the input, and exact distinct values and value
dictionaries in scans that each group several fields within a bound on the distinct values they
hold. It SHALL NOT run one query per field and statistic, and its results SHALL equal the
per-field computation.

#### Scenario: Wide file of low-cardinality fields
- **WHEN** a user runs `undatum stats` on a CSV with 24 columns of three values each
- **THEN** the input is scanned once for the per-field statistics and once per four dictionary
  fields (7 scans instead of about 100)

#### Scenario: High-cardinality fields
- **WHEN** several fields have about as many distinct values as there are records
- **THEN** their exact distinct counts are computed in scans of at most 2,000,000 estimated
  distinct values, so DuckDB's memory does not hold every field's values at once

### Requirement: Consistent Type Inference
`schema`, `analyze`, `stats`, `quality` and `schema-drift` SHALL infer field types with one shared
rule set, and SHALL report the same type for the same field of the same input. Values read as text
(CSV, TSV, and records undatum reads itself) SHALL get the first of integer, number, boolean, date
and datetime that at least 95% of their non-empty values convert to, in a sample of 10,000
records; placeholders (`n/a`, `null`, `-`, empty) SHALL count as empty, a value with a leading
zero SHALL make the field a string, and dates SHALL be ISO or day-first (`31.12.2020`,
`31/12/2020`, `31-12-2020`, `2020/12/31`). Typed inputs (JSON, Parquet) SHALL keep their own
types.

#### Scenario: Same file, same types
- **WHEN** a user runs `schema`, `stats`, `quality` and `schema-drift` on one CSV file
- **THEN** each field has the same type in all four reports

#### Scenario: A few bad values
- **WHEN** 2% of a CSV column's values are text and the rest are integers
- **THEN** every command reports the column as an integer

#### Scenario: Numbers as JSON strings
- **WHEN** a JSON Lines field holds strings such as `"2005"`
- **THEN** every command reports the field as a string

### Requirement: DuckDB Execution Through Arrow
Operations with a SQL form, `convert`, `sort`, `uniq` and `frequency` SHALL run in DuckDB for
inputs that DuckDB cannot read natively when pyarrow reads them as Arrow record batches (ORC,
Arrow IPC/Feather), and the records SHALL be identical to those of the Python engine.

#### Scenario: Frequency on an ORC file
- **WHEN** a user runs `undatum frequency events.orc -f region`
- **THEN** DuckDB computes the counts from Arrow batches of the `region` column
- **AND** the result equals the result of `--engine python`, including missing values

#### Scenario: Format without an Arrow reader
- **WHEN** pyarrow cannot read the input as Arrow batches (XLSX, Avro, Feather v1)
- **THEN** the operation runs on the Python engine as before

### Requirement: CSV Header as the Python Reader Reads It
Every DuckDB read of a CSV or TSV file SHALL take the field names from its first line as the
Python reader does (names as written, every value text) instead of DuckDB's sniffer. A file whose
header DuckDB cannot use (an empty name, or names that differ only by case) SHALL be read by the
Python engine.

#### Scenario: Row longer than the header
- **WHEN** a CSV file has a row with more values than its header
- **THEN** `undatum count` reports every record with either engine
- **AND** DuckDB keeps the header's field names and drops the values beyond them

#### Scenario: Numeric header
- **WHEN** the first line of a CSV file is `1,2`
- **THEN** `schema`, `select` and `convert` use the field names `1` and `2` with either engine

#### Scenario: Repeated names
- **WHEN** a CSV header repeats a name (`a,a,b`)
- **THEN** the command runs on the Python engine

### Requirement: Non-UTF-8 CSV in DuckDB
When DuckDB's `encodings` extension is installed locally, CSV and TSV files in an encoding other
than UTF-8 SHALL be read by DuckDB in the encoding the Python reader uses (`--encoding`, or the
detected one), with the same records as the Python engine. Without the extension, or for an
encoding DuckDB cannot read with ASCII line endings, quotes and delimiters, the Python engine
SHALL read them.

#### Scenario: Windows-1251 CSV
- **WHEN** the `encodings` extension is installed and a user runs `undatum convert data.csv
  data.parquet` on a Windows-1251 CSV file
- **THEN** DuckDB converts it
- **AND** the records equal those of `--engine python`

#### Scenario: Extension missing
- **WHEN** the `encodings` extension is not installed
- **THEN** the Python engine reads the Windows-1251 file, as before

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

### Requirement: Validation Rules in DuckDB
For CSV and TSV input, `validate --rules` and `quality --rules` SHALL run field rules made of
required, data type, references, unique, numeric range, length, enum and pattern checks as one
DuckDB query, and SHALL report the same violations (rule, field, severity, row, value, message,
order) as the Python rules. Rules with `format`, `custom` or a cross-field condition, patterns
whose meaning differs in RE2, and values only Python reads as numbers SHALL be checked by the
Python engine.

#### Scenario: Same violations
- **WHEN** a user runs `undatum validate data.csv --rules rules.yml` with `--engine python` and
  with `--engine duckdb`
- **THEN** both reports list the same violations in the same order

#### Scenario: Rule only Python checks
- **WHEN** a rule file contains a `format: email` rule
- **THEN** the records are checked by the Python engine

### Requirement: ODCS Data Contract Validation
`undatum validate --rules` SHALL accept an Open Data Contract Standard (ODCS) v3 contract as well
as an undatum rule file. `contract.yaml#name` SHALL select a schema object; a contract with
several objects and no name SHALL fail with a configuration error that lists them.

The constraints of each property SHALL be checked record by record, as an undatum rule:
`required`, `unique`, a single `primaryKey`, `logicalType`, `enum`, and the `logicalTypeOptions`
`minLength`, `maxLength`, `pattern`, `format`, `minimum` and `maximum`.

The quality metrics `nullValues`, `missingValues`, `invalidValues`, `duplicateValues` and
`rowCount` SHALL be counted over the file and compared with their operator, in rows or percent.
Composite primary keys and the options `exclusiveMinimum`, `exclusiveMaximum` and `multipleOf`
SHALL be checked the same way. `sql`, `custom` and `text` checks SHALL be reported as not
checked and never run.

#### Scenario: Contract with a failing quality check
- **WHEN** a user runs `undatum validate data.csv --rules contract.yaml --format-out json` and a
  `nullValues` check with `mustBe: 0` and severity `error` counts empty values
- **THEN** the `contract` section lists the check as failed with the count
- **AND** the command exits with code 1

#### Scenario: Same violations on both engines
- **WHEN** the rules of a contract compile to SQL
- **THEN** `--engine duckdb` and `--engine python` print the same report

### Requirement: ODCS Contract Export
`undatum schema FILE --format odcs` SHALL write a draft ODCS v3.2.0 contract (YAML) with one
schema object for the file and one property per field, with its `logicalType` and `physicalType`.

#### Scenario: Exported contract checks its own file
- **WHEN** a user writes a contract with `undatum schema data.csv --format odcs` and validates
  `data.csv` against it
- **THEN** the file has no violations

### Requirement: Cached Command Results
`stats`, `schema`, `sniff`, `analyze`, `headers` and `count` SHALL store their result for a local
file in `~/.undatum/cache` and reuse it on a later run with the same file and options.
- A result SHALL be reused only when the file's real path, size and modification time, the
  undatum version and the options that change the result are the same.
- The output of a run that reuses a result SHALL equal the output of a run that computes it.
- The CLI SHALL use the cache unless `--no-cache`, `UNDATUM_CACHE=0` or the config
  `defaults: cache: false` turns it off.
- Library calls SHALL use it only when asked.
- A cache that cannot be read or written SHALL NOT change a command's result or exit code.

#### Scenario: Second run reads the cached result
- **WHEN** a user runs `undatum stats data.csv --json` twice and the file is unchanged
- **THEN** the second run prints the same document without reading the data

#### Scenario: Changed file is read again
- **WHEN** `data.csv` changes between two runs of `undatum stats data.csv`
- **THEN** the second run reads the file and prints its new statistics

### Requirement: Cache Management
`undatum cache list` SHALL list the cached files with their results and sizes (`--json`:
`undatum.cache/1`). `undatum cache clear` SHALL remove all entries, and `--stale` only those whose
file is missing or changed.

#### Scenario: Clearing stale entries
- **WHEN** a cached file is deleted and the user runs `undatum cache clear --stale`
- **THEN** its entries are removed and the entries of unchanged files stay

