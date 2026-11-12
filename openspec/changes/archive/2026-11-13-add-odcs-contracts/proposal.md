# Change: Open Data Contract Standard (ODCS) Contracts

## Why
Data contracts describe what a dataset promises: its fields, their types and constraints, and
quality thresholds. The Open Data Contract Standard (ODCS, Bitol project of the Linux Foundation,
v3.2.0 of September 2026) is the open format for them. undatum already infers schemas and checks
rule files, but it cannot read or write a contract, so teams that keep ODCS contracts check files
with other tools. This is item 19 ("compatibility with ODCS") of the October 2026 engine review
(`analysis/2026-10-28-undatum-engines-and-competitors.md`).

## What Changes
- **Contracts as rule files:** `validate --rules` accepts an ODCS contract (`kind: DataContract`).
  - `contract.yaml#orders` selects the schema object `orders` of a contract with several.
- **Property constraints become record rules.** `required`, `unique`, a single `primaryKey`,
  `logicalType`, `enum` and the `logicalTypeOptions` undatum rules express (`minLength`,
  `maxLength`, `pattern`, `format`, `minimum`, `maximum`) become one undatum rule per property.
  - They are checked like hand-written rules, on both engines.
  - ECMA-262 patterns match anywhere in the value, as ODCS specifies.
- **Quality metrics become contract checks**, counted over the file in one more pass and compared
  with their operator in rows or percent: `nullValues`, `missingValues`, `invalidValues`,
  `duplicateValues` (also across properties) and `rowCount`.
  - Composite primary keys, `exclusiveMinimum`, `exclusiveMaximum` and `multipleOf` are
    checked the same way.
- **Reporting:** the report adds a `contract` section (checks and the parts not checked) in text and
  JSON (`undatum.validate/1`, a new optional key). A failed check of severity `error` exits with 1;
  `warning` does so with `--fail-on-warnings`.
- **Not checked:** `sql`, `custom` and `text` quality checks, other types and options are listed as
  not checked. SQL from a contract file is not run, because a contract from elsewhere could run any
  SQL.
- **Export:** `schema --format odcs` writes a draft ODCS v3.2.0 contract for the inferred schema.

## Impact
- Affected specs: `data-processing`.
- Affected code: `undatum/validate/odcs.py` (new), `undatum/common/validation_rules.py`,
  `undatum/cmds/validator.py`, `undatum/cmds/schemer.py`, `undatum/common/results.py`, CLI help,
  tests and documentation.
