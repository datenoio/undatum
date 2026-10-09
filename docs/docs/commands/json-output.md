---
title: "JSON output"
description: "Machine-readable results of informational commands, their schemas, and JSON errors"
---
# JSON output

Commands that report information rather than records print one JSON document with `--json`
(the same as `--format-out json`). Nothing else goes to stdout, so the output can be piped
to `jq` or read by scripts and agents:

```bash
undatum count data.csv --json
undatum headers data.csv --json
undatum stats data.csv --json
```

```json
{
  "schema": "undatum.count/1",
  "file": "data.csv",
  "rows": 3
}
```

| Command | Schema |
|---------|--------|
| `count` | `undatum.count/1` |
| `headers` | `undatum.headers/1` |
| `sniff` | `undatum.sniff/1` |
| `stats` | `undatum.stats/1` |
| `schema` (undatum's own format) | `undatum.schema/1` |
| `schema --validate` | `undatum.schema-validation/1` |
| `diff` | `undatum.diff/1` |
| `diff --schema` | `undatum.schema-diff/1` |
| `schema-drift` | `undatum.schema-drift/1` |
| `validate --rules` | `undatum.validate/1` |
| `validate --fields ... --rule ...` | `undatum.validate-rule/1` |
| `analyze` | `undatum.analyze/1` |
| `quality` | `undatum.quality/1` |
| `validate --list-rules` | `undatum.validate-rules/1` |
| `formats list` | `undatum.formats/1` |
| `config show` | `undatum.config/1` |

Record commands (`head`, `frequency`, `uniq`, `select`, ...) are different: with `--json` /
`-O json` they print a JSON array of records, without an envelope. `schema --format
jsonschema|cerberus|avro|parquet` prints that standard format as it is.

## Versions

The `schema` key names the layout and its major version. Adding a key is not a breaking
change; removing or renaming a key, or changing its type, raises the version
(`undatum.stats/1` becomes `undatum.stats/2`), and the CHANGELOG says so. Check `schema`
before reading a document:

```python norun
import json, subprocess

result = json.loads(subprocess.run(
    ["undatum", "count", "data.csv", "--json"], capture_output=True, text=True, check=True
).stdout)
assert result["schema"] == "undatum.count/1"
print(result["rows"])
```

## Errors

With `--json` or `--format-out json`, errors are JSON too: one object on stderr, and the
usual [exit code](/getting-started/troubleshooting) (1 user error, 2 usage, configuration or
missing dependency, 3 system, 4 internal, 130 interrupted).

```bash norun
undatum stats missing.csv --json
```

```json
{
  "error": {
    "code": "file_not_found",
    "message": "File not found: 'missing.csv'\nCheck that the file path is correct and the file exists.",
    "exit_code": 1,
    "details": {"file_path": "missing.csv"}
  }
}
```

| Code | Exit code | Meaning |
|------|-----------|---------|
| `file_not_found` | 1 | An input file does not exist |
| `validation_error` | 1 | An option value or field name is not valid |
| `format_error` | 1 | The file format is unknown or cannot be written |
| `invalid_rules` | 1 | A validation rule file is malformed |
| `invalid_value` | 1 | A value could not be processed |
| `usage_error` | 2 | Unknown option, missing argument |
| `configuration_error` | 2 | Bad configuration |
| `dependency_missing` | 2 | An optional extra is not installed |
| `permission_denied` | 3 | A file cannot be read or written |
| `database_error` | 3 | A database query or connection failed |
| `internal_error` | 4 | A bug — please report it |
| `interrupted` | 130 | Ctrl-C |

## Layouts

Each layout is also published as a JSON Schema file (linked below).

<!-- BEGIN GENERATED: result-schemas -->

### `undatum.count/1`

Number of records in a file. Printed by `undatum count --json`. [JSON Schema](pathname:///schemas/undatum.count.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.count/1` |
| `file` | string | yes | Input path |
| `rows` | integer | yes | Number of records |

### `undatum.headers/1`

Field names of a file. Printed by `undatum headers --json`. [JSON Schema](pathname:///schemas/undatum.headers.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.headers/1` |
| `file` | string | yes | Input path |
| `fields` | array | yes | Field names in file order (nested fields as dotted paths) |

### `undatum.sniff/1`

Detected file properties. Printed by `undatum sniff --json`. [JSON Schema](pathname:///schemas/undatum.sniff.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.sniff/1` |
| `file` | string | yes | Input path |
| `filetype` | string | yes | Detected format id (csv, jsonl, parquet, ...) |
| `compression` | string or null |  | Compression codec (gz, zst, ...), null if none |
| `encoding` | string or null |  | Text encoding, null for binary formats |
| `delimiter` | string or null |  | Field delimiter of delimited text, else null |
| `has_header` | boolean or null |  | Whether the first line is a header (CSV/TSV) |
| `record_count` | integer | yes | Number of records |
| `sample_size` | integer |  | Records sampled for field types |
| `fields` | object | yes | Field name -> type and up to 3 examples |

### `undatum.stats/1`

Field statistics. Printed by `undatum stats --json`. [JSON Schema](pathname:///schemas/undatum.stats.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.stats/1` |
| `count` | integer | yes | Records profiled |
| `num_fields` | integer | yes | Number of fields |
| `fieldtypes` | object | yes | Field -> detected type |
| `fields` | array | yes | Per-field statistics |
| `dictkeys` | array |  | Fields with few distinct values |
| `dicts` | object |  | Value lists of the dictionary fields |
| `debug` | object |  | Engine diagnostics (engine, timings); not stable |

### `undatum.schema/1`

Inferred table schema (undatum's own format). Printed by `undatum schema --json`. [JSON Schema](pathname:///schemas/undatum.schema.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.schema/1` |
| `id` | string |  | Table id (file name) |
| `key` | string |  | Hash of the field list |
| `num_cols` | integer |  | Number of fields |
| `num_records` | integer |  | Records read (-1 when not counted) |
| `is_flat` | boolean |  | No nested fields |
| `description` | string or null |  | Description (with --autodoc) |
| `fields` | array | yes | Fields: name, ftype, is_array, description, ... |
| `files` | array or null |  | Files with this schema (schema-bulk) |
| `success` | boolean |  | Inference succeeded |
| `error` | string or null |  | Error message when inference failed |

### `undatum.schema-validation/1`

Rows checked against the inferred schema. Printed by `undatum schema --validate --json`. [JSON Schema](pathname:///schemas/undatum.schema-validation.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.schema-validation/1` |
| `valid` | boolean | yes | No invalid rows |
| `stats` | object | yes | valid, invalid, total, errors_by_field |
| `invalid_sample` | array |  | Up to 20 invalid rows with their errors |

### `undatum.diff/1`

Records added, removed and changed between two files. Printed by `undatum diff --json`. [JSON Schema](pathname:///schemas/undatum.diff.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.diff/1` |
| `file1` | string | yes | Old file |
| `file2` | string | yes | New file |
| `key` | array or null |  | Key fields (null: records compared whole) |
| `summary` | object | yes | file1_count, file2_count, added_count, removed_count, changed_count |
| `added` | array |  | Records only in file2 (not with --summary-only) |
| `removed` | array |  | Records only in file1 (not with --summary-only) |
| `changed` | array |  | Changed records with key, old and new (not with --summary-only) |

### `undatum.schema-diff/1`

Schema changes between two files or declared schemas. Printed by `undatum diff --schema --json`. [JSON Schema](pathname:///schemas/undatum.schema-diff.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.schema-diff/1` |
| `old` | string | yes | Baseline file or schema |
| `new` | string | yes | Compared file or schema |
| `summary` | object | yes | Changes per kind: added, removed, type, nullability |
| `changes` | array | yes | Changes: kind, field, old and new type or nullability |
| `renames` | array | yes | Likely renames: old, new, name_similarity, value_overlap |

### `undatum.schema-drift/1`

Schema changes of a set of files against a baseline. Printed by `undatum schema-drift --json`. [JSON Schema](pathname:///schemas/undatum.schema-drift.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.schema-drift/1` |
| `baseline` | string | yes | Baseline file or schema |
| `summary` | object | yes | files (compared) and drifted (with changes) |
| `files` | array | yes | Per file: file, summary, changes, renames |

### `undatum.validate/1`

Rule-file validation report. Printed by `undatum validate --rules --json`. [JSON Schema](pathname:///schemas/undatum.validate.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.validate/1` |
| `statistics` | object | yes | total_records, total_violations, errors, warnings, info, passed |
| `violations_by_field` | object |  | Field -> number of violations |
| `violations_by_rule` | object |  | Rule -> number of violations |
| `violations` | array | yes | Violations (at most --max-violations) |

### `undatum.validate-rules/1`

Built-in validation rules. Printed by `undatum validate --list-rules --json`. [JSON Schema](pathname:///schemas/undatum.validate-rules.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.validate-rules/1` |
| `rules` | array | yes | Rules: name, description, params, extra |
| `keys` | object | yes | Rule-file keys that are checks (required, unique, ...) |

### `undatum.validate-rule/1`

Values checked against one built-in rule. Printed by `undatum validate --rule --json`. [JSON Schema](pathname:///schemas/undatum.validate-rule.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.validate-rule/1` |
| `rule` | string | yes | Rule name, e.g. common.email |
| `field` | string | yes | Checked field |
| `mode` | string |  | invalid, valid, all or stats |
| `statistics` | object | yes | total, invalid, novalue, share (percent invalid) |
| `records` | array |  | Checked values with a FIELD_valid flag (omitted with --mode stats) |

### `undatum.quality/1`

Data quality report with a pass/fail verdict. Printed by `undatum quality --json`. [JSON Schema](pathname:///schemas/undatum.quality.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.quality/1` |
| `file` | string | yes | Input path |
| `summary` | object | yes | rows, fields, empty_values, violations per severity (null without --rules) |
| `fields` | array | yes | Per field: name, type, values, nulls, null_rate, distinct, conformance, top_values |
| `schema_check` | object | yes | expected, inferred types, changes and renames against --schema |
| `violations` | object | yes | by_severity, by_rule and a sample of rule violations |
| `verdict` | object | yes | passed and the threshold checks (name, target, value, limit, passed) |

### `undatum.analyze/1`

File analysis report. Printed by `undatum analyze --json`. [JSON Schema](pathname:///schemas/undatum.analyze.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.analyze/1` |
| `filename` | string | yes | Input path |
| `file_size` | integer |  | Size in bytes |
| `file_type` | string |  | Detected format id |
| `compression` | string |  | Compression codec or raw |
| `total_tables` | integer |  | Number of tables |
| `total_records` | integer |  | Number of records |
| `tables` | array | yes | Per-table structure: fields, types, descriptions |
| `metadata` | object |  | Encoding, delimiter and other file metadata |
| `success` | boolean |  | Analysis succeeded |
| `error` | string or null |  | Error message when analysis failed |

### `undatum.formats/1`

Supported formats and their capabilities. Printed by `undatum formats list --json`. [JSON Schema](pathname:///schemas/undatum.formats.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.formats/1` |
| `formats` | array | yes | Formats: id, readable, writable, ... |

### `undatum.config/1`

Effective CLI configuration. Printed by `undatum config show --json`. [JSON Schema](pathname:///schemas/undatum.config.v1.json)

| Key | Type | Always | Description |
|-----|------|--------|-------------|
| `schema` | string | yes | `undatum.config/1` |
| `files` | object | yes | Config files read: home, project |
| `defaults` | object | yes | Merged command defaults |

<!-- END GENERATED: result-schemas -->
