# Change: Schema Diff and Drift Detection

## Why
`diff` compares rows, and `schema-bulk` extracts schemas from many files, but nothing tells a
dataset owner that a new delivery added, removed, renamed or retyped columns. Schema drift is the
most common cause of broken downstream loads.

## What Changes
- `undatum diff --schema old.csv new.csv` (or `undatum schema diff`) compares inferred or declared
  schemas: added/removed fields, type changes, nullability changes, likely renames (by name
  similarity and value overlap).
- `undatum schema drift <dir-or-glob>` compares every file to a baseline schema
  (`--baseline schema.json` or the first file) and reports drift per file.
- Text, Markdown and JSON output; `--fail-on added|removed|type|any` sets a non-zero exit code
  for CI.

## Impact
- Affected specs: `data-diff`
- Affected code: `undatum/cmds/differ.py`, `undatum/cmds/schemer.py`, `undatum/common/schema_utils.py`
