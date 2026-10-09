## ADDED Requirements

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
