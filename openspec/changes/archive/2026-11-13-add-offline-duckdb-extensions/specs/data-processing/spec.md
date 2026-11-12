## ADDED Requirements

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
