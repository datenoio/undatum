## 1. Implementation
- [x] 1.1 Partitioning sink in `undatum/io/` with a bounded writer pool (`--max-open-files`)
- [x] 1.2 `split --hive` layout on top of the existing `--fields` split
- [x] 1.3 `convert --partition-by` with the DuckDB `PARTITION_BY` fast path
- [x] 1.4 Path sanitization for key values (Hive layout follows DuckDB/Hive: percent-encoding,
      `__HIVE_DEFAULT_PARTITION__` for null/empty; flat `split` names use `__null__`)

## 2. Tests and docs
- [x] 2.1 Round trip: read the partitioned directory with DuckDB and compare row counts
- [x] 2.2 High-cardinality test (keys > `--max-open-files`)
- [x] 2.3 Docs and cookbook entry
