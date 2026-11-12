## ADDED Requirements

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
