"""Commands that choose, order or reshape records."""

from typing import Annotated

import typer

from ..common import enable_verbose
from ..options import (
    AddOpt,
    ErrorLogOpt,
    FlattenNestedOpt,
    KeepNestedParentsOpt,
    MaxNestedDepthOpt,
    OnErrorOpt,
    QuoteCharOpt,
    TableNameOpt,
    TrustOpt,
    WhereOpt,
)
from ._app import data_app


@data_app.command()
def select(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    fields: Annotated[
        str, typer.Option(help="Comma-separated list of field names to select and reorder.")
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    format_in: Annotated[
        str,
        typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl', 'xlsx')."),
    ] = None,
    format_out: Annotated[
        str, typer.Option(help="Override output format (e.g., 'csv', 'jsonl').")
    ] = None,
    zipfile: Annotated[bool, typer.Option(help="Treat input file as a ZIP archive.")] = False,
    filter_expr: Annotated[
        str,
        typer.Option(
            "--filter",
            "--filter-expr",
            help="Filter expression to apply (e.g., \"`status` == 'active'\").",
        ),
    ] = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    table: TableNameOpt = None,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default), 'duckdb', or 'iterable'."),
    ] = None,
    duckdb_threads: Annotated[
        int, typer.Option(help="Number of threads for DuckDB engine.")
    ] = None,
    duckdb_memory: Annotated[
        str, typer.Option(help="Memory limit for DuckDB (e.g., '4GB', '512MB').")
    ] = None,
    duckdb_temp_dir: Annotated[str, typer.Option(help="Temporary directory for DuckDB.")] = None,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    where: WhereOpt = None,
    add: AddOpt = None,
):
    """Select or reorder columns from file.

    Supports CSV, JSONL, BSON, Excel (XLS/XLSX), and other iterable formats. Can also filter records.
    """
    from ...cmds.selector import Selector

    if verbose:
        enable_verbose()
    options = {
        "where": where,
        "add": add,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "fields": fields,
        "output": output,
        "encoding": encoding,
        "format_in": format_in,
        "format_out": format_out,
        "zipfile": zipfile,
        "filter": filter_expr,
        "start_page": start_page,
        "table": table,
        "engine": engine,
        "duckdb_threads": duckdb_threads,
        "duckdb_memory": duckdb_memory,
        "duckdb_temp_dir": duckdb_temp_dir,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Selector()
    acmd.select(input_file, options)


@data_app.command()
def enum(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    field: Annotated[
        str, typer.Option(help="Field name for the generated values (default: 'row_id').")
    ] = "row_id",
    type: Annotated[
        str, typer.Option(help="Type of value: 'number' (default), 'uuid', or 'constant'.")
    ] = "number",
    start: Annotated[
        int, typer.Option(help="Starting number for numeric enumeration (default: 1).")
    ] = 1,
    value: Annotated[
        str, typer.Option(help="Constant value to use when type is 'constant'.")
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
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Add row numbers, UUIDs, or constant values to records.

    Useful for adding unique identifiers or sequential numbers to data.
    """
    from ...cmds.enumerator import Enumerator

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "field": field,
        "type": type,
        "start": start,
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
    }
    acmd = Enumerator()
    acmd.enum(input_file, options)


@data_app.command()
def reverse(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    filetype: Annotated[
        str, typer.Option(help="Override file type detection (e.g., 'csv', 'jsonl').")
    ] = None,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default), 'duckdb', or 'iterable'."),
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
    """Reverse the order of rows in a data file.

    For large files, may require buffering. DuckDB engine provides optimization for supported formats.
    """
    from ...cmds.reverser import Reverser

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": filetype,
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
    acmd = Reverser()
    acmd.reverse(input_file, options)


@data_app.command()
def fixlengths(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    strategy: Annotated[str, typer.Option(help="Strategy: 'pad' (default) or 'truncate'.")] = "pad",
    value: Annotated[
        str, typer.Option(help="Value to use for padding (default: empty string).")
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
):
    """Ensure all rows have the same number of fields.

    Pads shorter rows or truncates longer rows to normalize field counts.
    Useful for data cleaning workflows.
    """
    from ...cmds.fixlengths import FixLengths

    if verbose:
        enable_verbose()
    options = {
        "output": output,
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
    }
    acmd = FixLengths()
    acmd.fixlengths(input_file, options)


@data_app.command()
def sort(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    by: Annotated[str, typer.Option(help="Comma-separated list of field names to sort by.")] = None,
    desc: Annotated[bool, typer.Option(help="Sort in descending order.")] = False,
    numeric: Annotated[
        str, typer.Option(help="Comma-separated list of field names to sort numerically.")
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    filetype: Annotated[
        str, typer.Option(help="Override file type detection (e.g., 'csv', 'jsonl').")
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
    low_memory: Annotated[
        bool,
        typer.Option(help="Force external merge sort (spill sorted runs to disk)."),
    ] = False,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Sort rows by one or more columns.

    Supports multiple sort keys, ascending/descending order, and numeric sorting.
    Uses external merge sort for large files (auto above 100k rows, or with --low-memory).
    """
    from ...cmds.sorter import Sorter

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "by": by,
        "desc": desc,
        "numeric": numeric,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": filetype,
        "engine": engine,
        "duckdb_threads": duckdb_threads,
        "duckdb_memory": duckdb_memory,
        "duckdb_temp_dir": duckdb_temp_dir,
        "low_memory": low_memory,
        "temp_dir": duckdb_temp_dir,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Sorter()
    acmd.sort(input_file, options)


@data_app.command()
def sample(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    n: Annotated[int, typer.Option(help="Number of rows to sample.")] = None,
    percent: Annotated[float, typer.Option(help="Percentage of rows to sample (0-100).")] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    format_in: Annotated[
        str, typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl').")
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
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    where: WhereOpt = None,
):
    """Randomly select rows from a data file.

    Uses reservoir sampling algorithm that doesn't require loading all data into memory.
    """
    from ...cmds.sampler import Sampler

    if verbose:
        enable_verbose()
    options = {
        "where": where,
        "output": output,
        "n": n,
        "percent": percent,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": format_in,
        "format_in": format_in,  # Support both names
        "engine": engine,
        "duckdb_threads": duckdb_threads,
        "duckdb_memory": duckdb_memory,
        "duckdb_temp_dir": duckdb_temp_dir,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Sampler()
    acmd.sample(input_file, options)


@data_app.command()
def search(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    pattern: Annotated[str, typer.Option(help="Regex pattern to search for.")] = None,
    fields: Annotated[
        str,
        typer.Option(
            help="Comma-separated list of field names to search in (default: all fields)."
        ),
    ] = None,
    ignore_case: Annotated[bool, typer.Option(help="Case-insensitive search.")] = False,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    format_in: Annotated[
        str, typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl').")
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
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    where: WhereOpt = None,
):
    """Filter rows using regex patterns.

    Searches across specified fields or all fields, outputting rows that match the pattern.
    """
    from ...cmds.searcher import Searcher

    if verbose:
        enable_verbose()
    options = {
        "where": where,
        "output": output,
        "pattern": pattern,
        "fields": fields,
        "ignore_case": ignore_case,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": format_in,
        "format_in": format_in,  # Support both names
        "engine": engine,
        "duckdb_threads": duckdb_threads,
        "duckdb_memory": duckdb_memory,
        "duckdb_temp_dir": duckdb_temp_dir,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Searcher()
    acmd.search(input_file, options)


@data_app.command()
def dedup(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    key_fields: Annotated[
        str,
        typer.Option(
            help="Comma-separated list of field names to use for deduplication (default: all fields)."
        ),
    ] = None,
    keep: Annotated[
        str, typer.Option(help="Which duplicate to keep: 'first' (default) or 'last'.")
    ] = "first",
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    filetype: Annotated[
        str, typer.Option(help="Override file type detection (e.g., 'csv', 'jsonl').")
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
    low_memory: Annotated[
        bool,
        typer.Option(help="Force disk-backed exact deduplication (spill keys to SQLite)."),
    ] = False,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Remove duplicate rows.

    Can deduplicate by all fields or specified key fields. Supports keeping first or last occurrence.
    Large unique-key sets automatically spill to disk; use --low-memory to force that path.
    """
    from ...cmds.deduplicator import Deduplicator

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "key_fields": key_fields,
        "keep": keep,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": filetype,
        "engine": engine,
        "duckdb_threads": duckdb_threads,
        "duckdb_memory": duckdb_memory,
        "duckdb_temp_dir": duckdb_temp_dir,
        "low_memory": low_memory,
        "temp_dir": duckdb_temp_dir,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Deduplicator()
    acmd.dedup(input_file, options)


@data_app.command()
def transpose(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
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
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Swap rows and columns.

    Transposes the data table, handling headers appropriately.
    """
    from ...cmds.transposer import Transposer

    if verbose:
        enable_verbose()
    options = {
        "output": output,
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
    acmd = Transposer()
    acmd.transpose(input_file, options)


@data_app.command()
def slice(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    start: Annotated[int, typer.Option(help="Start index (inclusive).")] = None,
    end: Annotated[int, typer.Option(help="End index (inclusive).")] = None,
    indices: Annotated[
        str, typer.Option(help="Comma-separated list of specific indices to extract.")
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    filetype: Annotated[
        str, typer.Option(help="Override file type detection (e.g., 'csv', 'jsonl').")
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
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Extract specific rows by range or index list.

    Supports range-based slicing (--start/--end) or index-based slicing (--indices).
    Uses DuckDB for efficient random access when supported.
    """
    from ...cmds.slicer import Slicer

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "start": start,
        "end": end,
        "indices": indices,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": filetype,
        "engine": engine,
        "duckdb_threads": duckdb_threads,
        "duckdb_memory": duckdb_memory,
        "duckdb_temp_dir": duckdb_temp_dir,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Slicer()
    acmd.slice(input_file, options)
