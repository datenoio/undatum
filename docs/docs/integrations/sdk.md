---
title: "Python SDK"
description: "Fluent Dataset API for read, transform, and write"
---
# Python SDK

Undatum provides a Python SDK for programmatic data processing with a fluent API that mirrors CLI commands.

Every method with its parameters is listed in the [SDK reference](/integrations/sdk-reference), generated from the docstrings.

### How a Dataset runs

A `Dataset` is a **lazy plan**: `read()` and every transform method return a new `Dataset`
with one more step and read nothing. The plan runs when you ask for results — iterating,
`write()`, `count()`, `head()`, `stats()`, `collect()` or a DataFrame export — and records
stream from step to step as Python objects:

- no intermediate files are written between steps, and a plan can run as many times as you
  iterate it;
- values keep their Python types between steps (`datetime.date`, `Decimal`, nested dicts and
  lists); only the final writer converts them;
- `write()` runs the whole plan as one DuckDB query when the source is CSV/TSV/JSON/JSON
  Lines/Parquet and every step has a SQL form (`rename`, `fill`, `replace`, `filter(pattern=)`,
  `select`, `limit`, `slice`); otherwise records stream through Python;
- invalid arguments (an unknown `keep=`, a bad regular expression) fail when the step is added;
  data errors surface when the plan runs.

```python
plan = Dataset.read("big.csv").rename({"a": "x"}).fill("x", value="0").dedup()
print(plan.explain())          # the steps, nothing read yet
plan.write("clean.parquet")    # reads big.csv once, streaming
rows = Dataset.from_records([{"a": 1}, {"a": 2}]).enum("row").collect()
```

Operations that need the whole input (`sort`, `reverse`, `dedup` with many keys,
`fill(strategy="backward")`) spill to temporary files inside the step and clean them up.

### Quick Start

```python
from undatum import Dataset

# Read data
ds = Dataset.read("data.jsonl")
ds = Dataset.read("workbook.xlsx", table="Sheet2")
ds = Dataset.read("nested.jsonl", flatten_nested=True)

# Chain transformations
ds = ds.fill("age", value=0).dedup(keys=["user_id"]).sort("name")

# Compute statistics (unfold nested dict fields onto dotted paths)
stats = ds.stats()
stats = Dataset.read("nested.jsonl").stats(flatten_nested=True)

# Write output
ds.write("output.parquet")

# Bulk-convert a directory or glob (same as convert --recursive)
Dataset.convert_many("./raw", "./out", to_ext="jsonl")
Dataset.convert_many(
    "./raw",
    "./out",
    to_ext="jsonl",
    filename_pattern="{stem}.converted.jsonl",
)
```

### Transform Methods

```python
# Fill missing values
ds = ds.fill("age", value=0)
ds = ds.fill(["name", "email"], value="N/A")
ds = ds.fill("status", strategy="forward")

# Rename fields
ds = ds.rename(mapping={"id": "user_id"})
ds = ds.rename(pattern="^old_", replacement="new_")

# Explode a delimited field into rows
ds = ds.explode("tags", separator=",")

# Add row numbers or UUIDs
ds = ds.enum(field="row_id", enum_type="number", start=1)

# Reverse row order
ds = ds.reverse()

# Remove duplicates
ds = ds.dedup()  # By all fields
ds = ds.dedup(keys=["user_id", "email"])
ds = ds.dedup(keys=["id"], keep="last")

# Sort data
ds = ds.sort("name")
ds = ds.sort(["date", "price"], desc=True)
ds = ds.sort("age", numeric=True)

# Filter rows
ds = ds.filter(pattern="error|warning")
ds = ds.filter(pattern="active", fields=["status"])
ds = ds.filter(query="`price` > 100")

# Select fields
ds = ds.select(["name", "email"])
ds = ds.select("user_id", filter_expr="`status` == 'active'")

# Join datasets
ds1 = Dataset.read("users.jsonl")
ds2 = Dataset.read("orders.jsonl")
ds = ds1.join(ds2, keys=["user_id"], join_type="left")

# Sample data
ds = ds.sample(n=1000)
ds = ds.sample(percent=10.0)

# Mask sensitive fields
ds = ds.mask(["email", "phone"], method="redact")
ds = ds.mask("user_id", method="hash", salt="my-salt")

# Replace text, drop excluded keys, append other files
ds = ds.replace("phone", "-", "", global_replace=True)
ds = ds.exclude("blocklist.csv", on="email")
ds = ds.concat("more.csv", Dataset.read("even_more.jsonl"))

# Windows and reshaping
ds = ds.limit(100).slice(10, 20)
ds = ds.fixlengths().transpose()
```

### Query and quality methods

```python
ds = Dataset.read("data.csv")
ds.uniq("country")                 # distinct values, first-seen order
ds.frequency(["country", "city"])  # [{"country": ..., "city": ..., "count": n}, ...]
ds.schema()                        # inferred schema of the first 1000 records
report = ds.validate("rules.yml")  # {"records": n, "valid": n, "violations": [...]}
```

### Analysis Methods

```python
# Compute statistics
stats = ds.stats(checkdates=True, engine="duckdb")

# Count rows
n = ds.count()

# Get first/last rows
rows = ds.head(20)
rows = ds.tail(20)

# Generate a Frictionless Data Package descriptor
result = ds.package(output="datapackage.json")
result = ds.package(output="datapackage.json", package_dir="out/package", autodoc=True)
```

### DataFrame and Typed-Row Interop

Datasets can be handed off to DataFrame libraries or iterated as typed objects,
delegating to iterabledata's adapters:

```python
# DataFrame conversion (pandas is bundled; Polars/Dask via extras)
df = Dataset.read("data.jsonl").to_pandas()
pdf = Dataset.read("data.parquet").to_polars()   # pip install "undatum[polars]"
ddf = Dataset.read("big.jsonl").to_dask()        # pip install "undatum[dask]"

# Chunked pandas frames for large files
for chunk in Dataset.read("big.csv").to_pandas(chunksize=100_000):
    ...

# Typed iteration
from dataclasses import dataclass

@dataclass
class Person:
    name: str
    age: int

for person in Dataset.read("people.csv").as_dataclasses(Person):
    print(person.name)

from pydantic import BaseModel

class PersonModel(BaseModel):
    name: str
    age: int

for person in Dataset.read("people.csv").as_pydantic(PersonModel):
    print(person.age)
```

### Cloud Storage

```python
# AWS S3
ds = Dataset.read("s3://bucket/data.jsonl")
ds.write("s3://bucket/output.parquet")

# Google Cloud Storage
ds = Dataset.read("gs://bucket/data.csv")
ds.write("gs://bucket/output.parquet")

# Azure Blob Storage
ds = Dataset.read("az://container/data.jsonl")
ds.write("az://container/output.parquet")

# Chain transforms on cloud input
ds = Dataset.read("s3://bucket/input.csv")
ds = ds.fill("age", value=0).dedup(keys=["id"])
ds.write("gs://bucket/output.jsonl")
```

Install `pip install "undatum[cloud]"` (or `undatum[s3]` for S3 only). See [Cloud Storage Support](/integrations/cloud) for credential setup.

### Method Chaining

All transform methods return new Dataset instances, enabling fluent pipelines:

```python
ds = (Dataset.read("data.jsonl")
      .fill("age", value=0)
      .dedup(keys=["user_id"])
      .sort("date", desc=True)
      .filter(query="`status` == 'active'")
      .select(["name", "email", "age"])
      .sample(n=1000))
ds.write("output.parquet")
```
