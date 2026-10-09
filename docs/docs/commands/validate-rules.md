---
title: "Validation rules"
description: "Built-in formats, rule keys, references and uniqueness for undatum validate --rules"
---
# Validation rules

A rule file lists checks per field; `undatum validate data.csv --rules rules.yml` reports
every record that breaks one. `undatum validate --list-rules` prints the same catalogue as
this page.

```yaml
rules:
  - name: country code
    field: country
    format: country            # ISO 3166-1 alpha-2 or alpha-3
  - field: amount
    type: number
    min: 0
  - field: day
    format: date
    formats: ["%d.%m.%Y"]
  - field: id
    required: true
    unique: true
  - field: country
    references: {file: countries.csv, field: code}
    severity: warning
```

Unknown format, rule type or custom names stop the run before any data is read (exit code 2)
and name the closest match. Paths in `references` are relative to the current directory or
to the rule file.

```bash
undatum validate --list-rules
undatum validate data.csv --rules rules.yml --json
undatum validate data.csv --rules rules.yml -O jsonl > violations.jsonl
```

With `-O jsonl` every line is one violation:
`{"rule", "field", "severity", "row", "value", "message", "rule_type"}`; the summary goes to
stderr. `--json` prints the [`undatum.validate/1`](/commands/json-output) report.

`unique` remembers every value of the field; above a million values it moves them to a
temporary SQLite file, so memory stays bounded. `references` loads the reference column the
same way. Rule files with `unique` ignore `--threads` (every record has to be seen by one
process).

## Reference

<!-- BEGIN GENERATED: rules -->

### Formats (`format: NAME`)

| Name | Valid values | Parameters |
|------|--------------|------------|
| `email` | An e-mail address (name@domain) |  |
| `url` | An absolute URL |  |
| `date` | A calendar date; ISO 8601 (2026-10-08) unless 'formats' is given | `formats`: strptime patterns, e.g. ['%d.%m.%Y'] |
| `datetime` | A date and time; ISO 8601 unless 'formats' is given | `formats`: strptime patterns |
| `phone` | A phone number: E.164 (+4930123456); national numbers with 'region' | `region`: ISO country code for national numbers<br/>needs `undatum[phone]` for all features |
| `country` | An ISO 3166-1 country code (DE, DEU) | `alpha`: '2', '3', 'numeric' or 'any' (default) |
| `currency` | An ISO 4217 currency code (EUR) |  |
| `language` | An ISO 639-1 language code (en; en-GB with a region) | `allow_region`: accept a region suffix such as en-GB (default true) |
| `iban` | An IBAN with a valid check sum |  |
| `uuid` | A UUID (any version) |  |
| `pattern` | The whole value matches a regular expression | `regex`: the regular expression |
| `integer` | A whole number |  |
| `number` | A number (integer or decimal) |  |
| `boolean` | true/false, yes/no or 1/0 |  |
| `ru.org.inn` | A Russian taxpayer number (INN) with valid check digits |  |
| `ru.org.ogrn` | A Russian company registration number (OGRN) |  |

### Rule keys

| Key | Checks |
|-----|--------|
| `required` | true: the field must be present and not empty (not_null) |
| `unique` | true: no value may repeat across the file |
| `min` / `max` | numeric range (inclusive) |
| `min_length` / `max_length` | text length range |
| `enum` | list of allowed values |
| `pattern` | regular expression the value must match (prefix match) |
| `references` | &#123;file, field&#125;: the value must exist in that field of another file |
| `condition` | cross-field rule: an expression over 'fields' (type: cross-field) |

<!-- END GENERATED: rules -->
