"""Commands that work on several inputs."""

from typing import Annotated

import typer

from ..common import enable_verbose
from ..options import (
    ErrorLogOpt,
    FlattenNestedOpt,
    JsonOpt,
    KeepNestedParentsOpt,
    MaxNestedDepthOpt,
    OnErrorOpt,
    QuoteCharOpt,
    Table2NameOpt,
    TableNameOpt,
    TrustOpt,
)
from ._app import data_app


@data_app.command()
def cat(
    input_files: Annotated[
        list[str], typer.Argument(help="Path(s) to input file(s). Multiple files can be specified.")
    ],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    mode: Annotated[
        str, typer.Option(help="Concatenation mode: 'rows' (default) or 'columns'.")
    ] = "rows",
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
    """Concatenate files by rows or columns.

    Row mode: appends files vertically. Column mode: combines files side-by-side.
    """
    from ...cmds.cat import Cat

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "mode": mode,
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
    acmd = Cat()
    acmd.cat(input_files, options)


@data_app.command()
def join(
    file1: Annotated[str, typer.Argument(help="Path to first input file.")],
    file2: Annotated[str, typer.Argument(help="Path to second input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    on: Annotated[
        str, typer.Option(help="Comma-separated list of key field names to join on.")
    ] = None,
    type: Annotated[
        str, typer.Option(help="Join type: 'inner' (default), 'left', 'right', or 'full'.")
    ] = "inner",
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    filetype1: Annotated[
        str, typer.Option(help="Override file type detection for first file.")
    ] = None,
    filetype2: Annotated[
        str, typer.Option(help="Override file type detection for second file.")
    ] = None,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default), 'duckdb', or 'python'."),
    ] = None,
    duckdb_threads: Annotated[
        int, typer.Option(help="Number of threads for DuckDB engine.")
    ] = None,
    duckdb_memory: Annotated[
        str, typer.Option(help="Memory limit for DuckDB (e.g., '4GB', '512MB').")
    ] = None,
    duckdb_temp_dir: Annotated[str, typer.Option(help="Temporary directory for DuckDB.")] = None,
    progress: Annotated[bool, typer.Option(help="Show progress bar.")] = False,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for the first file.")] = 0,
    table2: Table2NameOpt = None,
    start_page2: Annotated[
        int, typer.Option(help="Sheet index (0-based) for the second file.")
    ] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Perform relational join between two files.

    Supports inner, left, right, and full outer joins. Uses hash-based join for streaming formats
    and DuckDB SQL join for supported formats.
    """
    from ...cmds.joiner import Joiner

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "on": on,
        "type": type,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype1": filetype1,
        "filetype2": filetype2,
        "engine": engine,
        "duckdb_threads": duckdb_threads,
        "duckdb_memory": duckdb_memory,
        "duckdb_temp_dir": duckdb_temp_dir,
        "progress": progress,
        "table": table,
        "start_page": start_page,
        "table2": table2,
        "start_page2": start_page2,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Joiner()
    acmd.join(file1, file2, options)


@data_app.command()
def diff(
    file1: Annotated[str, typer.Argument(help="Path to first input file.")],
    file2: Annotated[str, typer.Argument(help="Path to second input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    key: Annotated[
        str, typer.Option(help="Comma-separated list of key field names to compare on.")
    ] = None,
    output_format: Annotated[
        str, typer.Option(help="Detailed output format: json, csv, markdown, html, or unified.")
    ] = None,
    summary_only: Annotated[
        bool, typer.Option(help="Show summary only (suppress detailed output).")
    ] = False,
    ignore_order: Annotated[
        bool, typer.Option(help="Treat datasets as unordered sets when no key is provided.")
    ] = False,
    numeric_tolerance: Annotated[
        float, typer.Option(help="Numeric tolerance for float comparisons.")
    ] = None,
    ignore_case: Annotated[
        bool, typer.Option(help="Case-insensitive comparison for strings.")
    ] = False,
    max_added_rows: Annotated[
        int, typer.Option(help="Fail if added rows exceed this threshold.")
    ] = None,
    max_removed_rows: Annotated[
        int, typer.Option(help="Fail if removed rows exceed this threshold.")
    ] = None,
    max_changed_rows: Annotated[
        int, typer.Option(help="Fail if changed rows exceed this threshold.")
    ] = None,
    format: Annotated[
        str, typer.Option(help="(Deprecated) Output format: 'json' or 'unified'.")
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
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for the first file.")] = 0,
    table2: Table2NameOpt = None,
    start_page2: Annotated[
        int, typer.Option(help="Sheet index (0-based) for the second file.")
    ] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    json_output: JsonOpt = False,
    schema: Annotated[
        bool,
        typer.Option(
            "--schema",
            help="Compare the schemas (added, removed, retyped fields, renames) instead of rows.",
        ),
    ] = False,
    fail_on: Annotated[
        str | None,
        typer.Option(
            "--fail-on",
            help="With --schema: exit with 1 on these changes (added, removed, type, "
            "nullability, any).",
        ),
    ] = None,
):
    """Compare two files and show differences.

    Outputs added, removed, and changed rows based on key fields.
    """
    from ...cmds.differ import Differ

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "key": key,
        "output_format": "json" if json_output else output_format,
        "summary_only": summary_only,
        "ignore_order": ignore_order,
        "numeric_tolerance": numeric_tolerance,
        "ignore_case": ignore_case,
        "max_added_rows": max_added_rows,
        "max_removed_rows": max_removed_rows,
        "max_changed_rows": max_changed_rows,
        "format": format,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": format_in,
        "table": table,
        "start_page": start_page,
        "table2": table2,
        "start_page2": start_page2,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    if schema:
        from ...cmds.drift import emit_report, parse_fail_on, run_schema_diff

        fail = parse_fail_on(fail_on)
        result = run_schema_diff(file1, file2, options)
        emit_report([result], str(options.get("output_format") or format or ""), output)
        if result.fails(fail):
            raise typer.Exit(1)
        return
    acmd = Differ()
    acmd.diff(file1, file2, options)


@data_app.command()
def exclude(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    exclude_file: Annotated[str, typer.Argument(help="Path to exclusion file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    on: Annotated[
        str, typer.Option(help="Comma-separated list of key field names to exclude on.")
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
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for the input file.")] = 0,
    table2: Table2NameOpt = None,
    start_page2: Annotated[
        int, typer.Option(help="Sheet index (0-based) for the exclusion file.")
    ] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Remove rows from input file where keys match exclusion file.

    Uses hash-based lookup for performance.
    """
    from ...cmds.excluder import Excluder

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "on": on,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": format_in,
        "table": table,
        "start_page": start_page,
        "table2": table2,
        "start_page2": start_page2,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Excluder()
    acmd.exclude(input_file, exclude_file, options)
