## ADDED Requirements

### Requirement: Lazy Execution Plan
Transform methods on `Dataset` SHALL record operations without reading data, and the plan SHALL
execute once when results are requested (write, iteration, count, statistics or DataFrame export).

#### Scenario: Building a chain reads nothing
- **WHEN** user calls `Dataset.read("big.csv").fill("a", value=0).dedup()`
- **THEN** no records are read until a terminal method is called

### Requirement: No Intermediate Files Between Steps
Executing an SDK chain SHALL stream records between steps without writing intermediate files,
except for operations that must spill to disk internally.

#### Scenario: Three-step chain
- **WHEN** user runs `Dataset.read("data.csv").rename(...).fill(...).write("out.parquet")`
- **THEN** no intermediate JSONL files are created

### Requirement: Typed Values Preserved Between Steps
Values SHALL keep their Python types between SDK steps and SHALL be converted only by the final
sink.

#### Scenario: Dates survive a chain
- **WHEN** a Parquet source has a date column and the user chains `rename` and `sort`
- **THEN** iterating the result yields `datetime.date` values for that column
