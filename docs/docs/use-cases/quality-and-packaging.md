---
title: "Quality and packaging"
description: "Validate, diff, mask, and publish Frictionless packages"
---
# Quality and packaging

Assess quality, encode reusable rules, and produce evidence before data is released.

## Gate a dataset release

```bash
undatum validate data.csv --rules rules.yml --format-out json \
  --violation-report violations.json --fail-on-warnings
```

Example rule files live in the [examples/validation-rules](https://github.com/datenoio/undatum/tree/master/examples/validation-rules) directory; the [rule library](/commands/validate-rules) lists the built-in formats (dates, phone numbers, ISO codes, IBAN, ...), `unique` and `references`.

## Report quality against thresholds

```bash
undatum quality data.csv --rules rules.yml -o report.html
```

`--thresholds` turns the report into a data contract: the command exits with 1 when a
threshold fails. See [`quality`](/commands/quality).

## Catch schema drift

```bash
undatum diff --schema data.csv data.jsonl
undatum schema-drift data.csv data.jsonl --fail-on removed,type
```

## Detect unintended changes

```bash
undatum diff previous.parquet current.parquet --key id --ignore-order \
  --max-changed-rows 0 --summary-only
```

## Publish a Frictionless package

```bash
undatum package create data.csv --package-dir release --output release/datapackage.json
undatum package validate release/datapackage.json
```

## Prepare a safe public extract

```bash
undatum mask source.csv --fields email,phone --method hash --salt "$SALT" --output public.csv
undatum doc public.csv --pii-detect --pii-mask-samples --output DATASET.md
```

See [`quality`](/commands/quality), [`validate`](/commands/validate), [`schema-drift`](/commands/schema-drift), [`package`](/commands/package), [`mask`](/commands/mask), and [`doc`](/commands/doc).
