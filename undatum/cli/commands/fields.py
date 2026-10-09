"""Commands that change field names or values."""

from typing import Annotated

import typer

from ..common import enable_verbose
from ..options import (
    EngineOpt,
    ErrorLogOpt,
    FlattenNestedOpt,
    KeepNestedParentsOpt,
    MaxNestedDepthOpt,
    OnErrorOpt,
    QuoteCharOpt,
    TableNameOpt,
    TrustOpt,
)
from ._app import data_app


@data_app.command()
def apply(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    fields: Annotated[
        str, typer.Option(help="Comma-separated list of field names (kept for compatibility).")
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = "utf8",
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    format_in: Annotated[
        str, typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl').")
    ] = None,
    zipfile: Annotated[bool, typer.Option(help="Treat input file as a ZIP archive.")] = False,
    script: Annotated[
        str, typer.Option(help="Path to Python script file containing transformation function.")
    ] = None,
    plugin: Annotated[
        str,
        typer.Option(help="Name of a registered transform plugin to apply instead of a script."),
    ] = None,
    filter_expr: Annotated[
        str,
        typer.Option(
            "--filter",
            "--filter-expr",
            help="Filter expression to apply before transformation.",
        ),
    ] = None,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Apply a transformation script to each record in the file.

    Executes a Python script that transforms each record, or a registered
    transform plugin when ``--plugin`` is given.
    """
    from ...cmds.transformer import Transformer

    if verbose:
        enable_verbose()
    options = {
        "delimiter": delimiter,
        "quotechar": quotechar,
        "fields": fields,
        "output": output,
        "encoding": encoding,
        "format_in": format_in,
        "zipfile": zipfile,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
        "filter": filter_expr,
        "script": script,
        "plugin": plugin,
    }
    acmd = Transformer()
    acmd.script(input_file, options)


@data_app.command()
def mask(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    fields: Annotated[
        str, typer.Option(help="Comma-separated list of fields to mask (e.g., 'email,phone,ssn').")
    ] = None,
    method: Annotated[
        str, typer.Option(help="Masking method: 'redact' (default), 'hash', or 'randomize'.")
    ] = "redact",
    salt: Annotated[
        str, typer.Option(help="Optional salt for hash method (for additional security).")
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    format_in: Annotated[
        str, typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl').")
    ] = None,
    format_out: Annotated[
        str, typer.Option(help="Override output file format (e.g., 'csv', 'jsonl').")
    ] = None,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Mask sensitive fields in a data file for anonymization.

    Supports three masking methods:
    - redact: Replace with fixed token (e.g., '***')
    - hash: Deterministic one-way hash (preserves joins, hides identities)
    - randomize: Replace with random but type-compatible values

    Examples:
        # Redact email and phone fields
        undatum mask data.csv --fields email,phone --method redact --output masked.csv

        # Hash user IDs (deterministic, preserves joins)
        undatum mask data.jsonl --fields user_id --method hash --output masked.jsonl

        # Randomize age and email fields
        undatum mask data.csv --fields age,email --method randomize --output masked.csv
    """
    from ...cmds.masker import Masker

    if verbose:
        enable_verbose()
    options = {
        "fields": fields,
        "method": method,
        "salt": salt,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "format_in": format_in,
        "format_out": format_out,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Masker()
    acmd.mask(input_file, output, options)


@data_app.command()
def fill(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    fields: Annotated[
        str, typer.Option(help="Comma-separated list of field names to fill (default: all fields).")
    ] = None,
    strategy: Annotated[
        str, typer.Option(help="Fill strategy: 'constant' (default), 'forward', or 'backward'.")
    ] = "constant",
    value: Annotated[
        str,
        typer.Option(help="Constant value to use for filling (required for 'constant' strategy)."),
    ] = "",
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    format_in: Annotated[
        str, typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl').")
    ] = None,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    engine: EngineOpt = None,
):
    """Fill empty or null values with specified values or strategies.

    Supports constant filling, forward-fill (use previous value), and backward-fill (use next value).
    """
    from ...cmds.filler import Filler

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "fields": fields,
        "strategy": strategy,
        "value": value,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": format_in,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
        "engine": engine,
    }
    acmd = Filler()
    acmd.fill(input_file, options)


@data_app.command()
def rename(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    map: Annotated[
        str, typer.Option(help="Field name mapping: 'old_name:new_name,old2:new2'.")
    ] = None,
    pattern: Annotated[
        str, typer.Option(help="Regex pattern to match field names (for regex-based renaming).")
    ] = None,
    replacement: Annotated[
        str, typer.Option(help="Replacement string for regex pattern (default: empty string).")
    ] = "",
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    format_in: Annotated[
        str, typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl').")
    ] = None,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    engine: EngineOpt = None,
):
    """Rename fields by exact mapping or regex patterns.

    Supports multiple field renames in one operation.
    """
    from ...cmds.renamer import Renamer

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "map": map,
        "pattern": pattern,
        "replacement": replacement,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": format_in,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
        "engine": engine,
    }
    acmd = Renamer()
    acmd.rename(input_file, options)


@data_app.command()
def explode(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    field: Annotated[str, typer.Option(help="Field name to split by separator.")] = None,
    separator: Annotated[str, typer.Option(help="Separator character (default: comma).")] = ",",
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    format_in: Annotated[
        str, typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl').")
    ] = None,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Split a column by separator into multiple rows.

    Creates one row per value in the specified field, duplicating other fields.
    """
    from ...cmds.exploder import Exploder

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "field": field,
        "separator": separator,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": format_in,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Exploder()
    acmd.explode(input_file, options)


@data_app.command()
def replace(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    field: Annotated[str, typer.Option(help="Field name to perform replacement in.")] = None,
    pattern: Annotated[str, typer.Option(help="Pattern to search for (string or regex).")] = None,
    replacement: Annotated[str, typer.Option(help="Replacement string.")] = "",
    regex: Annotated[bool, typer.Option(help="Treat pattern as regex.")] = False,
    global_replace: Annotated[
        bool, typer.Option(help="Replace all occurrences (default: replace first only).")
    ] = False,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    format_in: Annotated[
        str, typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl').")
    ] = None,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    engine: EngineOpt = None,
):
    """Perform string replacement in specified fields.

    Supports simple string replacement and regex-based replacement.
    """
    from ...cmds.replacer import Replacer

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "field": field,
        "pattern": pattern,
        "replacement": replacement,
        "regex": regex,
        "global": global_replace,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": format_in,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
        "engine": engine,
    }
    acmd = Replacer()
    acmd.replace(input_file, options)
