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

Example rule files live in the [examples/validation-rules](https://github.com/datenoio/undatum/tree/master/examples/validation-rules) directory.

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

See [`validate`](/commands/validate), [`package`](/commands/package), [`mask`](/commands/mask), and [`doc`](/commands/doc).
