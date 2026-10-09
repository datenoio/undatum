---
title: "Format support"
description: "Read/write/streaming matrix for 140+ formats"
slug: /formats
---
# Format support matrix

undatum supports **140+ formats** via [iterabledata](https://github.com/datenoio/iterabledata/)
(catalog size depends on the installed iterabledata version and optional extras).
Capabilities differ by format: many are **read-only**, some require extras, and streaming
support varies.

undatum requires **Python 3.10+** and **iterabledata ≥ 1.0.21** (installed with undatum), which
provides the open-data pack, lakehouse writes, codec profiles and Avro writes. Run
`undatum formats list` to see what your install actually exposes.

## How to inspect live capabilities

```bash
# Human-readable catalog
undatum formats list

# Capability matrix (read / write / streaming / maturity / native bulk)
undatum formats list --capabilities

# Named tables or sheets
undatum formats tables workbook.xlsx

# One format: memory model, selection pushdown, codecs, native bulk, example args
undatum formats describe parquet
undatum formats describe xml

# Machine-readable
undatum formats list --capabilities --json
```

## Core formats (typical CLI workflows)

| Format | Read | Write | Streaming | Notes |
|--------|------|-------|-----------|-------|
| CSV / TSV | yes | yes | yes | Delimiter auto-detected (comma, semicolon, tab, pipe), also inside `.gz`/`.zst`/`.bz2`/`.xz`/`.zip` |
| JSON Lines / NDJSON | yes | yes | yes | Preferred for nested records |
| JSON (array/object) | yes | yes | limited | Prefer JSONL for large files |
| Parquet | yes | yes | batched | Requires `pyarrow` (default dependency); codec profiles `fast`/`balanced`/`max` |
| Arrow / Feather | yes | yes | batched | Native batch convert path in iterabledata 1.0.17+ |
| Excel XLSX / XLS | yes | limited | sheet-based | `--table` / `--sheet` for a named sheet; `--start-page` for a 0-based index |
| XML | yes | limited | yes | Use `--tagname` for record elements |
| BSON | yes | yes | yes | |
| AVRO | yes | yes | batched | Writable since iterabledata 1.0.14 (lazy schema inference) |
| ORC | yes | yes | batched | Robust schema inference for unusual column names (1.0.14+) |
| YAML | yes | yes | limited | |
| DuckDB / SQLite files | yes | yes | table-based | Default table name derived from output filename when omitted (1.0.14+) |

Compression codecs commonly used with the above: `gz`/`gzip`, `zst`, `bz2`, `xz`, `lz4`, `zip`, `7z`.
Codec performance profiles (`fast`, `balanced`, `max`) are available through iterabledata;
`undatum repack` uses maximum compression by default.

Use `undatum repack` to recompress container-coded files at maximum compression, or to rewrite
Parquet/ORC/AVRO with format-native compression. See [`repack`](/commands/repack).

## Format families (non-exhaustive)

| Family | Examples | Notes |
|--------|----------|-------|
| Tabular text | `csv`, `tsv`, `psv` (RO), `ltsv`, `jsonl`/`ndjson`, `annotatedcsv`, `csvw`, `fwf`, `ssv`, `txt` | Core CLI path |
| Columnar / analytics | `parquet`, `orc`, `avro`, `arrow`, `geoparquet`, `zarr`, `vtx` (Vortex), `ddb` | Many need optional deps |
| Lakehouse / warehouse | `delta`, `iceberg`, `lance`, `hudi` (RO), `ducklake`, `paimon`, `paimon_row`, `paimon_mosaic` | Delta/Iceberg writable in iterabledata 1.0.18+; install via `pip install "undatum[lakehouse]"` (or `iterabledata[lakehouse]`) |
| Geospatial | `geojson`, `geojsonseq`, `topojson`, `flatgeobuf` (RO), `gml`, `gpx`, `shp`, `gpkg`, `kml`, `kmz` (RO), `fgdb`/`gdb`, `mif`, `asc`, `e00`, `las`, `bag`, `czml`, `mvt` (RO), `dxf` (RO) | Open-data GIS pack partly experimental; `flatgeobuf` needs `undatum[gis]` |
| Scientific / geophysical | `h5`, `nc`, `cdf`, `mat`, `npy`, `segy`, `grib2`, `mseed`, `cif`, `pdb`, `xyz`, `edi` | Often read-only; extras such as `mat`, `geophysical`, `lidar` |
| Statistical | `sas`, `sav`, `dta`, `rds`/`rda`, `px` (PC-Axis), `dbf`, `arff` | Read-only |
| Business / legacy | `mdb`/`accdb`, `lotus123` (`123`/`wk1`), `xlsb` | Access needs `undatum[access]` |
| Binary serialization | `mp` (MessagePack), `cbor`, `ion`, `smile`, `ubj`, `bencode`, `der` (ASN.1), `pb`, `capnp`, `thrift`, `fbs` (RO)/`flexbuf` | Protobuf, Cap'n Proto, Thrift and FlatBuffers need a schema |
| Configuration / notation | `yml` (YAML), `toml`, `ini`, `hocon`, `edn` | |
| Database dumps | `copy` (PostgreSQL `COPY`), `sql` (`mysqldump`) | |
| ML / big data | `tfrecord`, `libsvm`, `seq` (Hadoop SequenceFile), `rio` (RecordIO), `beam`, `ckpt` (Flink) | |
| Web, mail, directory | `htm` (RO), `mht`, `arc` (WARC), `cdx`, `eml`, `mbox`, `ics`, `ldif` | |
| Containers | `zip`, `zipxml` (RO, XML inside ZIP), `tar` (RO multi-member), WebDataset | TAR tags records with `_member` |
| Genomic / bio | `genomic_vcf`, `bam`, `sam`, `bed*`, `gff3`/`gtf`, `cram`, `fa` (FASTA), `fq` (FASTQ) | VCF vs vCard `.vcf` disambiguated by content |
| Graph / RDF | `graphml`, `gexf`, `gv` (Graphviz, RO), `jsonld`, `nt`, `nq`, `n3` (RO), `ttl`, `trig`, `trix` (RO), `hdt` | HDT via open-data pack |
| Logs / feeds / streams | `log`, `gelf`, `cef`, `ilp` (InfluxDB line protocol), `pcap` (RO), `rss` (RO), `kafka`, `pulsar`, `otlp-json`, `otlp-protobuf` | OTLP is experimental (`otlp` extra of iterabledata) |
| Niche open data | `iati`, `fst`, `webdataset` | Experimental; optional extras |

## Important caveats

1. **Read-only formats exist.** Do not assume every format listed by `formats list` can be a
   conversion *target*. undatum fails fast with writable-format suggestions when you pick a
   read-only output. Hudi remains read-only pending Python SDK write support.
2. **Extras.** Some connectors need optional installs (`undatum[cloud]`, `undatum[api]`,
   `undatum[extract]`, database drivers, or undatum extras that forward iterabledata packs:
   `undatum[lakehouse]`, `undatum[gis]`, `undatum[scientific]`, `undatum[access]`,
   `undatum[compression]`). You can still install iterabledata extras directly if you prefer.
3. **Large files.** Prefer `--low-memory` on `convert` / `sort` / `dedup`, and Parquet or
   JSONL over in-memory JSON arrays. Parquet/Arrow writers buffer bounded batches
   (iterabledata 1.0.17+).
4. **Python version.** undatum and iterabledata require **Python ≥ 3.10**; on Python 3.9 pip
   resolves to undatum 1.6.0.
5. **Security / error policy** (iterabledata 1.0.16+): XML parsers disable external entities;
   pickle reads warn unless `trust=True` (`undatum convert --trust`, and the same flag on
   other read commands); malformed rows raise `FormatParseError` unless you pass
   `--on-error skip` or `--on-error warn`. Pair with `--error-log errors.jsonl` to keep a JSONL
   record of skipped rows.

For the authoritative list, always trust `undatum formats list --capabilities` for your
installed version. Upstream release notes:
[iterabledata CHANGELOG](https://github.com/datenoio/iterabledata/blob/main/CHANGELOG.md).


## Catalog notes

undatum supports **140+ formats** through iterabledata (exact catalog depends on the iterabledata version and optional extras). Format detection is automatic from file extensions and content; override with `--format-in` / `--format-out` when needed. Run `undatum formats list` for the authoritative catalog on your installation.

### Core tabular formats

| Format | Extensions / ids | Notes |
|--------|------------------|-------|
| **CSV / TSV** | `.csv`, `.tsv` (`csv`, alias `tsv`) | Delimiter and encoding auto-detected |
| **JSON Lines** | `.jsonl`, `.ndjson` (`jsonl`, alias `ndjson`) | One JSON object per line; ideal for streaming |
| **JSON** | `.json` | Array or object documents |
| **Parquet / ORC / Avro** | `.parquet`, `.orc`, `.avro` | Columnar and binary row formats; Avro is writable (iterabledata 1.0.14+) |
| **Arrow / Feather** | `.arrow`, `.feather` | Bounded batch I/O; native batch convert path available |
| **Excel** | `.xls`, `.xlsx`, `.xlsb`, `.ods` | Named sheet via `--table` / `--sheet`; `--start-page` for a 0-based index |
| **BSON** | `.bson` | Binary JSON (MongoDB) |
| **DuckDB / SQLite** | `.ddb`, `.duckdb`, `.sqlite`, `.db` | Table name defaults from output filename when omitted |

### Structured, geospatial, scientific, and lakehouse

- **XML** — convert with `--tagname` to specify the record element (XXE-hardened parsers in iterabledata 1.0.16+)
- **YAML / TOML / INI** — config and metadata formats (`yml`, `toml`, `ini`)
- **Geospatial** — `geojson`, `geojsonseq`, `geoparquet`, `fgb`, `gpx`, `shp`, `gpkg`, `kml`, FileGDB (`fgdb`), MapInfo MIF, LAS, …
- **Lakehouse** — Delta and Iceberg support bounded writes (1.0.18+); also Lance, DuckLake, Paimon; Hudi remains read-only. Install with `pip install "undatum[lakehouse]"`
- **Scientific / statistical** — `h5`, `nc`, `mat`, `segy`, `grib2`, `sas`, `sav`, `dta`, and others (many read-only)
- **Containers** — ZIP; read-only TAR multi-member archives (`tar` / `.tgz`); WebDataset
- **Graph / RDF** — `graphml`, `gexf`, `jsonld`, `nt`, `ttl`, `trig`, `hdt`, …

### Compression

Read and write through compressed containers without manual decompression: **GZ, XZ, BZ2, ZIP, ZSTD, LZ4, 7Z**, and other codecs supported by iterabledata. Codec profiles `fast` / `balanced` / `max` are available in iterabledata 1.0.17+; `undatum repack` defaults to maximum compression.

```bash
# Process JSONL inside a ZIP or XZ archive
undatum headers --format-in jsonl data.zip
undatum count data.jsonl.xz
```

### Choosing a format

| Use case | Recommended formats |
|----------|---------------------|
| Streaming ETL / logs | JSON Lines, CSV |
| Analytics / data lakes | Parquet, ORC, Avro, Delta, Iceberg |
| API interchange | JSON, JSON Schema |
| Packaging / catalogs | Frictionless Data Package (`undatum package`) |
| Geospatial pipelines | GeoJSON / GeoJSONSeq → GeoParquet |

Inspect read/write capabilities before converting:

```bash
undatum formats describe parquet
undatum formats list --writable --capabilities
```

Per-format reader/writer details live in the upstream [iterabledata formats docs](https://datenoio.github.io/iterabledata/formats/).
