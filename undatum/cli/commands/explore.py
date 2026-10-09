"""Commands that look at a dataset: fields, values, counts, previews, charts."""

import logging
import sys
from typing import Annotated

import typer

from ..common import enable_verbose
from ..options import (
    EngineOpt,
    ErrorLogOpt,
    FlattenNestedOpt,
    JsonOpt,
    KeepNestedParentsOpt,
    MaxNestedDepthOpt,
    OnErrorOpt,
    QuoteCharOpt,
    TableNameOpt,
    TrustOpt,
    WhereOpt,
)
from ._app import data_app

logger = logging.getLogger(__name__)


@data_app.command()
def uniq(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    fields: Annotated[
        str, typer.Option(help="Comma-separated list of field names to extract unique values from.")
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    filetype: Annotated[
        str, typer.Option(help="Override file type detection (e.g., 'csv', 'jsonl', 'xlsx').")
    ] = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    table: TableNameOpt = None,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default), 'duckdb', or 'iterable'."),
    ] = None,
    filter_expr: Annotated[
        str,
        typer.Option(
            "--filter",
            "--filter-expr",
            help="Filter expression to apply before extracting uniques.",
        ),
    ] = None,
    format_out: Annotated[
        str,
        typer.Option(
            help="Output format: 'csv' (default) or 'json' (also inferred from --output)."
        ),
    ] = None,
    json_output: JsonOpt = False,
):
    """Extract all unique values from specified field(s).

    Returns unique values or unique combinations if multiple fields are specified.
    Supports CSV, JSONL, Excel (XLS/XLSX), and other iterable formats.
    """
    from ...cmds.selector import Selector

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "fields": fields,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "filetype": filetype,
        "start_page": start_page,
        "table": table,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
        "engine": engine,
        "filter": filter_expr,
        "format_out": "json" if json_output else format_out,
    }
    acmd = Selector()
    acmd.uniq(input_file, options)


@data_app.command()
def headers(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    fields: Annotated[
        str, typer.Option(help="Field filter (kept for API compatibility, not currently used).")
    ] = None,  # pylint: disable=unused-argument
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    limit: Annotated[
        int, typer.Option(help="Maximum number of records to scan for field detection.")
    ] = 10000,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    format_in: Annotated[
        str,
        typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl', 'xml')."),
    ] = None,
    format_out: Annotated[
        str, typer.Option(help="Override output format (e.g., 'csv', 'json').")
    ] = None,
    zipfile: Annotated[bool, typer.Option(help="Treat input file as a ZIP archive.")] = False,
    filter_expr: Annotated[
        str,
        typer.Option(help="Filter expression (kept for API compatibility, not currently used)."),
    ] = None,  # pylint: disable=unused-argument
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    json_output: JsonOpt = False,
):
    """Returns fieldnames of the file. Supports XML, CSV, JSON, BSON.

    Scans the input file and returns all detected field/column names.
    """
    from ...cmds.selector import Selector

    if verbose:
        enable_verbose()
    # fields and filter_expr kept for API compatibility but not currently used
    options = {
        "output": output,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "limit": limit,
        "format_in": format_in,
        "format_out": "json" if json_output else format_out,
        "zipfile": zipfile,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Selector()
    acmd.headers(input_file, options)


@data_app.command()
def stats(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    dictshare: Annotated[
        int, typer.Option(help="Dictionary share threshold (0-100) for type detection.")
    ] = None,
    format_in: Annotated[
        str, typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl').")
    ] = None,
    format_out: Annotated[
        str,
        typer.Option(
            help="Output format: 'json', 'html', or 'markdown' (also inferred from --output extension)."
        ),
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    zipfile: Annotated[bool, typer.Option(help="Treat input file as a ZIP archive.")] = False,
    checkdates: Annotated[bool, typer.Option(help="Enable automatic date field detection.")] = True,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    progress: Annotated[bool, typer.Option(help="Show progress bar (default: True).")] = True,
    no_progress: Annotated[
        bool, typer.Option(help="Disable progress bar (for non-interactive use).")
    ] = False,
    engine: Annotated[
        str | None,
        typer.Option(
            help="Engine to use for statistics computation: 'auto' (detect), 'duckdb' (DuckDB engine), or 'iterable' (row-by-row)."
        ),
    ] = None,
    threads: Annotated[
        int,
        typer.Option(
            help=(
                "Worker processes for Python/iterable-engine chunk parallelism. "
                "Omit for sequential. For DuckDB, prefer --duckdb-threads / engine settings."
            )
        ),
    ] = None,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    json_output: JsonOpt = False,
):
    """Generate detailed statistics about a dataset.

    Provides field types, uniqueness counts, min/max/average lengths,
    and optional date field detection.
    """
    from ...cmds.statistics import StatProcessor

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "dictshare": dictshare,
        "zipfile": zipfile,
        "format_in": format_in,
        "format_out": "json" if json_output else format_out,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "checkdates": checkdates,
        "encoding": encoding,
        "verbose": verbose,
        "progress": progress if not no_progress else False,
        "no_progress": no_progress,
        "engine": engine,
        "threads": threads,
        "table": table,
        "start_page": start_page,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
    }
    acmd = StatProcessor(nodates=not checkdates)
    acmd.stats(input_file, options)


# Register `profile` as an alias of `stats`
data_app.command(name="profile")(stats)


@data_app.command()
def frequency(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    fields: Annotated[
        str, typer.Option(help="Comma-separated list of field names to calculate frequency for.")
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    filetype: Annotated[
        str, typer.Option(help="Override file type detection (e.g., 'csv', 'jsonl', 'xlsx').")
    ] = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    table: TableNameOpt = None,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default), 'duckdb', or 'python'."),
    ] = None,
    threads: Annotated[
        int,
        typer.Option(
            help=(
                "Worker processes for Python/iterable-engine frequency counting. "
                "Omit for sequential. For DuckDB, use --duckdb-threads."
            )
        ),
    ] = None,
    duckdb_threads: Annotated[
        int, typer.Option(help="Number of threads for DuckDB engine.")
    ] = None,
    duckdb_memory: Annotated[
        str, typer.Option(help="Memory limit for DuckDB (e.g., '4GB', '512MB').")
    ] = None,
    duckdb_temp_dir: Annotated[str, typer.Option(help="Temporary directory for DuckDB.")] = None,
    filter_expr: Annotated[
        str,
        typer.Option(
            "--filter",
            "--filter-expr",
            help="Filter expression to apply before counting frequencies.",
        ),
    ] = None,
    format_out: Annotated[
        str,
        typer.Option(
            help="Output format: 'csv' (default) or 'json' (also inferred from --output)."
        ),
    ] = None,
    json_output: JsonOpt = False,
):
    """Calculate frequency distribution for specified fields.

    Counts occurrences of each unique value in the specified field(s).
    Supports CSV, JSONL, Excel (XLS/XLSX), and other iterable formats.
    """
    from ...cmds.selector import Selector

    if verbose:
        enable_verbose()
    options = {
        "delimiter": delimiter,
        "quotechar": quotechar,
        "fields": fields,
        "output": output,
        "encoding": encoding,
        "filetype": filetype,
        "start_page": start_page,
        "table": table,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
        "engine": engine,
        "threads": threads,
        "duckdb_threads": duckdb_threads,
        "duckdb_memory": duckdb_memory,
        "duckdb_temp_dir": duckdb_temp_dir,
        "filter": filter_expr,
        "format_out": "json" if json_output else format_out,
    }
    acmd = Selector()
    acmd.frequency(input_file, options)


@data_app.command()
def count(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
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
    format_out: Annotated[
        str | None,
        typer.Option("--format-out", "-O", help="Output format: text (default) or json."),
    ] = None,
    json_output: JsonOpt = False,
    where: WhereOpt = None,
):
    """Count the number of rows in a data file.

    Returns the total number of data rows (excluding header if present).
    With DuckDB engine, counting is instant for supported formats.
    """
    from ...cmds.counter import Counter

    if verbose:
        enable_verbose()
    options = {
        "where": where,
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
        "format_out": "json" if json_output else format_out,
    }
    acmd = Counter()
    acmd.count(input_file, options)


@data_app.command()
def head(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    n: Annotated[int, typer.Option(help="Number of rows to extract (default: 10).")] = 10,
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
    where: WhereOpt = None,
):
    """Extract the first N rows from a data file.

    Useful for quick data inspection.
    """
    from ...cmds.head import Head

    if verbose:
        enable_verbose()
    options = {
        "where": where,
        "output": output,
        "n": n,
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
    acmd = Head()
    acmd.head(input_file, options)


@data_app.command()
def tail(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    n: Annotated[int, typer.Option(help="Number of rows to extract (default: 10).")] = 10,
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
    """Extract the last N rows from a data file.

    Uses efficient buffering for large files.
    """
    from ...cmds.tail import Tail

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "n": n,
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
    acmd = Tail()
    acmd.tail(input_file, options)


@data_app.command()
def table(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    limit: Annotated[
        int, typer.Option(help="Maximum number of rows to display (default: 20).")
    ] = 20,
    fields: Annotated[
        str, typer.Option(help="Comma-separated list of field names to display.")
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
    """Display data in a formatted, aligned table for inspection.

    Uses the rich library to create a nicely formatted table output.
    """
    from ...cmds.table import TableFormatter

    if verbose:
        enable_verbose()
    options = {
        "limit": limit,
        "fields": fields,
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
    acmd = TableFormatter()
    acmd.table(input_file, options)


@data_app.command()
def sniff(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    format: Annotated[
        str, typer.Option(help="Output format: 'text' (default), 'json', or 'yaml'.")
    ] = None,
    format_out: Annotated[
        str,
        typer.Option(
            help="Output format: 'text' (default), 'json', or 'yaml'. "
            "Also inferred when --output ends in .json/.yaml/.yml."
        ),
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
    json_output: JsonOpt = False,
):
    """Detect file properties (delimiter, encoding, types, record count).

    Analyzes the file and reports detected properties.
    """
    from ...cmds.sniffer import Sniffer

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "format": format,
        "format_out": "json" if json_output else format_out,
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
    acmd = Sniffer()
    acmd.sniff(input_file, options)


@data_app.command()
def plot(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    field: Annotated[
        str, typer.Option(help="Field name(s) to plot (comma-separated for multiple fields).")
    ],
    type: Annotated[
        str,
        typer.Option(
            help="Plot type: 'histogram', 'bar', 'scatter', 'line', or 'auto' (default: auto)."
        ),
    ] = "auto",
    output: Annotated[
        str, typer.Option(help="Output file path. If not specified, displays plot.")
    ] = None,
    format: Annotated[
        str,
        typer.Option(
            help="Output format: 'png', 'svg', or 'pdf' (default: auto-detect from output file)."
        ),
    ] = None,
    title: Annotated[str, typer.Option(help="Plot title.")] = None,
    xlabel: Annotated[str, typer.Option(help="X-axis label.")] = None,
    ylabel: Annotated[str, typer.Option(help="Y-axis label.")] = None,
    width: Annotated[float, typer.Option(help="Figure width in inches (default: 10).")] = 10,
    height: Annotated[float, typer.Option(help="Figure height in inches (default: 6).")] = 6,
    dpi: Annotated[int, typer.Option(help="Resolution for raster formats (default: 100).")] = 100,
    color: Annotated[str, typer.Option(help="Color scheme name (matplotlib colormap).")] = None,
    style: Annotated[
        str, typer.Option(help="Matplotlib style name (e.g. 'ggplot', 'seaborn-v0_8').")
    ] = None,
    filter_expr: Annotated[
        str,
        typer.Option(
            "--filter",
            "--filter-expr",
            help="Filter expression applied before plotting.",
        ),
    ] = None,
    aggregate: Annotated[
        str,
        typer.Option(help="Aggregation for bar charts: count (default), sum, mean, or none."),
    ] = "count",
    value_field: Annotated[
        str, typer.Option(help="Numeric field to sum/mean when --aggregate is sum or mean.")
    ] = None,
    top_n: Annotated[
        int, typer.Option(help="Keep the top N aggregated groups for bar charts.")
    ] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    table: TableNameOpt = None,
    quotechar: QuoteCharOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Generate data visualizations from data files.

    Supports multiple plot types: histograms for numerical distributions, bar charts for
    categorical frequencies, scatter plots for relationships, and line plots for time series.

    Examples:
        # Generate histogram for numerical field
        undatum plot data.csv --field age --type histogram --output age_dist.png

        # Generate bar chart for categorical field
        undatum plot data.csv --field status --type bar

        # Generate scatter plot for two fields
        undatum plot data.csv --field x,y --type scatter --output scatter.png

        # Auto-detect plot type
        undatum plot data.csv --field age --output age_plot.png

        # Filter then plot a bar chart of the top categories
        undatum plot data.csv --field city --type bar --filter "`status` == 'active'" --top-n 10
    """
    from ...cmds.plotter import Plotter

    if verbose:
        enable_verbose()

    try:
        plotter = Plotter()
        plotter.plot(
            fromfile=input_file,
            field=field,
            plot_type=type,
            output=output,
            output_format=format,
            title=title,
            xlabel=xlabel,
            ylabel=ylabel,
            width=width,
            height=height,
            dpi=dpi,
            color=color,
            style=style,
            filter=filter_expr,
            aggregate=aggregate,
            value_field=value_field,
            top_n=top_n,
            table=table,
            quotechar=quotechar,
            start_page=start_page,
            trust=trust,
            on_error=on_error,
            error_log=error_log,
            flatten_nested=flatten_nested,
            max_nested_depth=max_nested_depth,
            keep_nested_parents=keep_nested_parents,
        )
    except ImportError as e:
        logger.error(f"Plotting requires matplotlib: {e}")
        logger.error("Install with: pip install matplotlib")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Plot generation failed: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)
