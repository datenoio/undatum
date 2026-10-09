---
title: "Format conversion"
description: "Convert CSV, JSONL, XML, Excel, and Parquet with undatum"
---
# Format conversion

Convert any readable iterabledata format to any writable one. There is no fixed pairwise matrix — inspect your install with `undatum formats list --writable`.

## CSV to Parquet

```bash
undatum convert people.csv people.parquet
undatum stats people.parquet
```

For multi-GB inputs:

```bash
undatum convert huge.jsonl.zst huge.parquet --low-memory
```

## XML to JSON Lines

```bash
undatum convert --tagname item data.xml data.jsonl
```

## Excel sheet to Parquet

```bash
undatum formats tables workbook.xlsx
undatum convert workbook.xlsx sales.parquet --table Sheet2
```

## Bulk directory convert

```bash
undatum convert ./raw ./processed --recursive --to-ext parquet
undatum convert ./raw ./out --recursive --to-ext jsonl --filename-pattern "{stem}.converted.jsonl"
```

## Cloud to cloud

```bash norun
undatum convert s3://bucket/input.jsonl gs://other/output.parquet
```

See [`convert`](/commands/convert), [`repack`](/commands/repack), and the [format matrix](/formats/).
