## ADDED Requirements

### Requirement: Bounded Memory for Row-Wise Transforms
Commands that transform records one at a time (rename, fill, replace, search, select, enum,
explode, exclude, fixlengths, head) SHALL process input as a stream with peak memory independent
of input size, and SHALL stay within 300 MB peak resident memory for a 1-million-row, 5-column CSV.

#### Scenario: Large CSV rename
- **WHEN** user runs `undatum rename big.csv --map "a:x" --output out.csv` on 1 million rows
- **THEN** peak resident memory is at most 300 MB

#### Scenario: Memory does not grow with input
- **WHEN** the same command runs on 250 thousand and on 1 million rows
- **THEN** peak memory differs by less than 20%

### Requirement: Engine Pushdown for SQL-Expressible Transforms
When the input is readable by DuckDB and the engine is `auto` or `duckdb`, SQL-expressible
transforms SHALL execute in DuckDB and SHALL produce the same records as the Python engine.

#### Scenario: Rename runs in DuckDB
- **WHEN** user runs `undatum -v rename data.parquet --map "a:x" --output out.parquet`
- **THEN** the debug log reports the DuckDB engine
- **AND** the output equals the result of `--engine python`

### Requirement: Unified Read and Write Layer
All record-reading and record-writing commands SHALL use one input layer and one output layer that
support every iterabledata format, compression by extension, standard input/output and cloud URIs,
and output files SHALL be written atomically.

#### Scenario: Failed write leaves no partial file
- **WHEN** a command fails halfway while writing `out.parquet`
- **THEN** `out.parquet` does not exist after the command exits

#### Scenario: Whole-dataset operations spill to disk
- **WHEN** user runs `undatum reverse big.jsonl --output out.jsonl` with a memory cap smaller than
  the input
- **THEN** the command completes using temporary disk storage
