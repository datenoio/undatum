"""Typer option aliases shared by the data commands."""

from typing import Annotated

import typer

TableNameOpt = Annotated[
    str | None,
    typer.Option(
        "--table",
        "--sheet",
        help="Table or sheet name for multi-table sources (Excel, SQLite, lakehouse).",
    ),
]

Table2NameOpt = Annotated[
    str | None,
    typer.Option(
        "--table2",
        "--sheet2",
        help="Table or sheet name for the second file (Excel, SQLite, lakehouse).",
    ),
]

FlattenNestedOpt = Annotated[
    bool,
    typer.Option(
        "--flatten-nested",
        help="Unfold nested dict / array-of-dict fields into dotted paths (e.g. city.lat).",
    ),
]

MaxNestedDepthOpt = Annotated[
    int | None,
    typer.Option(
        "--max-nested-depth",
        help="With --flatten-nested, maximum nest depth to unfold (engine default 5).",
    ),
]

KeepNestedParentsOpt = Annotated[
    bool,
    typer.Option(
        "--keep-nested-parents/--no-keep-nested-parents",
        help="With --flatten-nested, keep parent dict/array fields alongside dotted children.",
    ),
]

TrustOpt = Annotated[
    bool,
    typer.Option(
        "--trust",
        help="Acknowledge pickle deserialization risk when reading pickle sources.",
    ),
]

OnErrorOpt = Annotated[
    str | None,
    typer.Option(
        "--on-error",
        help="Parse-error policy: raise (default), skip, or warn.",
    ),
]

ErrorLogOpt = Annotated[
    str | None,
    typer.Option(
        "--error-log",
        help="Append parse errors as JSONL (use with --on-error skip or warn).",
    ),
]

QuoteCharOpt = Annotated[
    str | None,
    typer.Option(
        "--quotechar",
        help="CSV quote character (iterabledata default '\"' when omitted).",
    ),
]

# doc/document: one switch for output samples (with --pii-detect) and AI samples.
DocMaskSamplesOpt = Annotated[
    bool | None,
    typer.Option(
        "--pii-mask-samples/--no-pii-mask-samples",
        help=(
            "Redact detected PII in sample records (with --pii-detect) and mask likely PII in "
            "rows sent to the AI provider (--autodoc masks for remote providers by default)."
        ),
        show_default=False,
    ),
]

EngineOpt = Annotated[
    str | None,
    typer.Option(help="Processing engine: auto (default), duckdb, or python."),
]

JsonOpt = Annotated[
    bool,
    typer.Option(
        "--json",
        help="Print the result as one JSON document (same as --format-out json).",
    ),
]

WhereOpt = Annotated[
    str | None,
    typer.Option(
        "--where",
        help=(
            "Keep records where this SQL condition is true (DuckDB syntax), e.g. "
            "\"amount > 100 AND city = 'Berlin'\". Text values are typed automatically."
        ),
    ),
]

AddOpt = Annotated[
    list[str] | None,
    typer.Option(
        "--add",
        help="Add a computed column: 'name = SQL expression', e.g. 'total = price * qty' "
        "(repeatable; an existing name is replaced in place).",
    ),
]

MaxOpenFilesOpt = Annotated[
    int,
    typer.Option(
        "--max-open-files",
        help="Partition files open at once; more distinct keys write additional part files.",
    ),
]
