"""CLI command for the optional interactive TUI."""

from __future__ import annotations

import sys
from typing import Annotated

import typer

from ..common.errors import ValidationError
from ..tui.deps import require_tui_dependencies
from ..tui.session import DEFAULT_SAMPLE_LIMIT
from .common import enable_verbose


def _is_tty() -> bool:
    return bool(getattr(sys.stdin, "isatty", lambda: False)() and sys.stdout.isatty())


def tui(
    input_file: Annotated[
        str | None,
        typer.Argument(help="Path to a data file. Opens a file picker if omitted."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option(help="Sample rows to show in the grid (default 200, max 5000)."),
    ] = DEFAULT_SAMPLE_LIMIT,
    delimiter: Annotated[
        str | None,
        typer.Option(help="CSV delimiter character (auto-detected when omitted)."),
    ] = None,
    quotechar: Annotated[
        str | None,
        typer.Option(
            "--quotechar",
            help="CSV quote character (iterabledata default '\"' when omitted).",
        ),
    ] = None,
    encoding: Annotated[
        str | None,
        typer.Option(help="File encoding (e.g. 'utf8', 'latin1')."),
    ] = None,
    format_in: Annotated[
        str | None,
        typer.Option(help="Override input file format detection (e.g. 'csv', 'jsonl')."),
    ] = None,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default), 'duckdb', or 'python'."),
    ] = None,
    table: Annotated[
        str | None,
        typer.Option(
            "--table",
            "--sheet",
            help="Table or sheet name for multi-table sources (Excel, SQLite, lakehouse).",
        ),
    ] = None,
    start_page: Annotated[
        int,
        typer.Option(help="Sheet index (0-based) for Excel files."),
    ] = 0,
    trust: Annotated[
        bool,
        typer.Option(
            "--trust",
            help="Acknowledge pickle deserialization risk when reading pickle sources.",
        ),
    ] = False,
    on_error: Annotated[
        str | None,
        typer.Option(
            "--on-error",
            help="Parse-error policy: raise (default), skip, or warn.",
        ),
    ] = None,
    error_log: Annotated[
        str | None,
        typer.Option(
            "--error-log",
            help="Append parse errors as JSONL (use with --on-error skip or warn).",
        ),
    ] = None,
    flatten_nested: Annotated[
        bool,
        typer.Option(
            "--flatten-nested",
            help="Unfold nested dict / array-of-dict fields into dotted paths (e.g. city.lat).",
        ),
    ] = False,
    max_nested_depth: Annotated[
        int | None,
        typer.Option(
            "--max-nested-depth",
            help="With --flatten-nested, maximum nest depth to unfold (engine default 5).",
        ),
    ] = None,
    keep_nested_parents: Annotated[
        bool,
        typer.Option(
            "--keep-nested-parents/--no-keep-nested-parents",
            help="With --flatten-nested, keep parent dict/array fields alongside dotted children.",
        ),
    ] = True,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Open an interactive TUI to preview a sampled dataset.

    Requires the optional Textual extra and a real terminal.
    The grid shows a bounded sample (default 200 rows), not the whole file.
    Keys: q quit, ? help, o open, s profile, f frequency, / filter, e export,
    w convert, v validate, m mask, p pipeline, colon palette, ctrl+s SQL.

    Examples:
        undatum tui data.csv
        undatum tui data.parquet --limit 500
        undatum tui workbook.xlsx --table Sheet2
        undatum tui nested.jsonl --flatten-nested
    """
    if verbose:
        enable_verbose()
    require_tui_dependencies()
    if not _is_tty():
        raise ValidationError(
            "undatum tui needs an interactive terminal. Use undatum table / stats / sql instead."
        )
    from ..tui.app import run_tui

    options = {
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "format_in": format_in,
        "engine": engine,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    run_tui(input_file, options=options, limit=limit)
