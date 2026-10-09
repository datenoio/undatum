"""What each data command reads, writes and how much memory it needs.

The command reference pages show this as a "capabilities" line
(``scripts/generate_cli_reference.py``). Engines are not listed here: a command supports
``auto``/``duckdb``/``python`` exactly when it has an ``--engine`` option.

Keep the ``memory`` text honest: "streaming" means memory does not grow with the input.
Commands that load every row are marked as such until they are ported to the streaming
operation core.
"""

from __future__ import annotations

from dataclasses import dataclass

ANY_READABLE = "any readable format"
ANY_WRITABLE = "any writable format; CSV/TSV/JSON/JSON Lines on stdout"
REPORT = "report (see `--format-out`)"

STREAMING = "streaming"


@dataclass(frozen=True)
class Capability:
    """Input, output and memory profile of one command."""

    reads: str = ANY_READABLE
    writes: str = ANY_WRITABLE
    memory: str = STREAMING


CAPABILITIES: dict[str, Capability] = {
    "analyze": Capability(writes=REPORT, memory="bounded: a sample of `--limit` records"),
    "apply": Capability(memory="streaming, two passes over the input"),
    "cat": Capability(),
    "convert": Capability(),
    "count": Capability(writes="a number"),
    "dedup": Capability(
        memory="streaming; up to 100,000 keys in memory, then a disk index "
        "(`--low-memory` uses the disk index from the start)"
    ),
    "diff": Capability(writes=REPORT, memory="keys of both files in memory"),
    "doc": Capability(writes=REPORT, memory="bounded: a sample plus streaming statistics"),
    "enum": Capability(),
    "exclude": Capability(memory="streaming; the keys of the exclusion file are kept in memory"),
    "explode": Capability(),
    "extract": Capability(
        reads="PDF, DOCX, DOC, HTML and images (OCR)",
        writes="CSV, JSON, JSON Lines, Parquet or a data package",
        memory="one document at a time",
    ),
    "fill": Capability(memory="streaming; `--strategy backward` spills to disk"),
    "fixlengths": Capability(memory="streaming, two passes over the input"),
    "flatten": Capability(writes="one `field: value` line per value"),
    "fmt": Capability(
        reads="CSV and TSV",
        writes="CSV with the chosen dialect",
        memory="streaming, two passes over the input",
    ),
    "frequency": Capability(memory="grows with the number of distinct values"),
    "head": Capability(memory="bounded: the first `--limit` rows"),
    "headers": Capability(writes="field names (text or JSON)"),
    "ingest": Capability(writes="a database table, collection or index"),
    "join": Capability(
        memory="Python engine indexes the second file in memory; DuckDB works out of core"
    ),
    "mask": Capability(),
    "migrate-script": Capability(
        reads="shell scripts, Makefiles, Markdown and pipeline YAML (text files)",
        writes="a diff, or the rewritten files with --write",
        memory="one file at a time",
    ),
    "plot": Capability(writes="a chart image (PNG, SVG, PDF)", memory="loads the plotted fields"),
    "rename": Capability(),
    "repack": Capability(
        writes="the same format, recompressed (Parquet/ORC/Avro natively)",
        memory="streaming (record batches)",
    ),
    "replace": Capability(),
    "reverse": Capability(memory="spills to disk in chunks of 50,000 records"),
    "sample": Capability(
        memory="bounded: `--limit` rows (reservoir); `--percent` counts the file first"
    ),
    "schema": Capability(writes=REPORT, memory="bounded: a sample of records"),
    "schema-bulk": Capability(writes=REPORT, memory="bounded: a sample of records per file"),
    "quality": Capability(
        writes="a Markdown, HTML or JSON report",
        memory="DuckDB profiles CSV/JSON/Parquet out of core; other formats are loaded into DuckDB",
    ),
    "schema-drift": Capability(writes=REPORT, memory="bounded: a sample of records per file"),
    "search": Capability(),
    "select": Capability(),
    "slice": Capability(memory="streaming; reading stops after the last selected record"),
    "sniff": Capability(writes=REPORT, memory="bounded: the beginning of the file"),
    "sort": Capability(
        memory="in memory up to 100k rows, external merge sort on disk above "
        "(or with `--low-memory`); DuckDB spills to disk"
    ),
    "split": Capability(writes="one file per chunk or per value"),
    "sql": Capability(
        reads="formats DuckDB reads (CSV, TSV, JSON, JSON Lines, Parquet, ...)",
        writes="query results (see `--format-out`)",
        memory="DuckDB (spills to disk)",
    ),
    "stats": Capability(
        writes=REPORT, memory="streaming aggregates; distinct values grow with cardinality"
    ),
    "table": Capability(writes="a table in the terminal", memory="bounded: `--limit` rows"),
    "tail": Capability(memory="bounded: the last `--limit` rows"),
    "transpose": Capability(memory="one output record at a time; reads the input once per field"),
    "tui": Capability(writes="interactive terminal view", memory="bounded: a sample of rows"),
    "uniq": Capability(memory="grows with the number of distinct values"),
    "validate": Capability(writes="validation report or the (in)valid rows"),
    "web": Capability(writes="local web page", memory="bounded: a sample of rows"),
    "db load": Capability(writes="a database table, collection or index"),
    "db dump": Capability(reads="a database table or query", memory="streaming (batches)"),
    "db query": Capability(reads="a database query", memory="streaming (batches)"),
}
