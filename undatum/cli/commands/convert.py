"""Format conversion and file-level commands."""

import os
from typing import Annotated

import typer

from ...common.errors import ValidationError
from ..common import enable_verbose
from ..options import (
    AddOpt,
    ErrorLogOpt,
    FlattenNestedOpt,
    KeepNestedParentsOpt,
    MaxNestedDepthOpt,
    MaxOpenFilesOpt,
    OnErrorOpt,
    QuoteCharOpt,
    TableNameOpt,
    TrustOpt,
    WhereOpt,
)
from ._app import data_app


@data_app.command()
def convert(
    input_file: Annotated[str, typer.Argument(help="Path to input file to convert.")],
    output: Annotated[str, typer.Argument(help="Path to output file.")],
    delimiter: Annotated[
        str | None,
        typer.Option(help="CSV delimiter character (auto-detected when omitted)."),
    ] = None,
    quotechar: QuoteCharOpt = None,
    compression: Annotated[
        str | None,
        typer.Option(help="Output compression codec (e.g. 'brotli', 'snappy', 'gzip')."),
    ] = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = "utf8",
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    flatten_data: Annotated[
        bool, typer.Option(help="Flatten nested data structures into flat records.")
    ] = False,
    prefix_strip: Annotated[
        bool, typer.Option(help="Strip XML namespace prefixes from element names.")
    ] = True,
    start_line: Annotated[
        int, typer.Option(help="Line number (0-based) to start reading from.")
    ] = 0,
    start_page: Annotated[
        int, typer.Option(help="Page number (0-based) to start from for Excel files.")
    ] = 0,
    table: TableNameOpt = None,
    tagname: Annotated[
        str, typer.Option(help="XML tag name that contains individual records.")
    ] = None,
    format_in: Annotated[
        str,
        typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl', 'xml')."),
    ] = None,
    format_out: Annotated[
        str, typer.Option(help="Override output file format (e.g., 'csv', 'jsonl', 'parquet').")
    ] = None,
    batch_size: Annotated[
        int, typer.Option(help="Number of records per conversion batch.")
    ] = 50000,
    scan_limit: Annotated[
        int, typer.Option(help="Records to sample for output schema detection.")
    ] = 1000,
    atomic: Annotated[
        bool,
        typer.Option(help="Write to a temp file and rename on success (local output only)."),
    ] = False,
    threads: Annotated[
        int,
        typer.Option(
            help=(
                "Worker processes for Python-engine chunk parallelism "
                "(single-file convert and bulk --recursive). "
                "Omit for sequential processing. DuckDB uses its own threading "
                "(see --engine / duckdb thread settings); not nested around DuckDB COPY."
            )
        ),
    ] = None,
    progress: Annotated[bool, typer.Option(help="Show progress bar.")] = True,
    low_memory: Annotated[
        bool,
        typer.Option(
            help="Prefer spill-to-disk / smaller batches for large-file conversion "
            "(DuckDB COPY when possible)."
        ),
    ] = False,
    engine: Annotated[
        str | None,
        typer.Option(help="Conversion engine: 'auto' (default), 'duckdb', or 'python'."),
    ] = None,
    recursive: Annotated[
        bool,
        typer.Option(
            help="Bulk-convert a directory or glob pattern; OUTPUT is treated as a directory."
        ),
    ] = False,
    to_ext: Annotated[
        str,
        typer.Option(
            help="Target extension for bulk conversion (e.g. 'parquet'). Defaults to --format-out."
        ),
    ] = None,
    filename_pattern: Annotated[
        str | None,
        typer.Option(
            "--filename-pattern",
            help=(
                "Bulk output name pattern with {name}, {stem}, {ext} "
                "(used with --recursive; default replaces the extension via --to-ext)."
            ),
        ),
    ] = None,
    profile: Annotated[
        str | None,
        typer.Option(
            help="Codec performance profile for compressed output: fast, balanced, or max."
        ),
    ] = None,
    level: Annotated[
        int | None,
        typer.Option(
            "--level",
            help=(
                "Explicit compression level for compressed output (overrides --profile). "
                "Same codecargs compression_level as iterabledata / undatum repack."
            ),
        ),
    ] = None,
    native_batch: Annotated[
        bool | None,
        typer.Option(
            "--native-batch/--no-native-batch",
            help=(
                "Use native columnar batch conversion when both formats support it. "
                "Default: auto-enable with --low-memory."
            ),
        ),
    ] = None,
    strict_native: Annotated[
        bool,
        typer.Option(
            "--strict-native",
            help="Fail if native batch conversion is requested but unsupported.",
        ),
    ] = False,
    columns: Annotated[
        str | None,
        typer.Option(help="Comma-separated columns to convert (native batch projection)."),
    ] = None,
    row_range: Annotated[
        str | None,
        typer.Option(help="Row range to convert as START:END (native batch)."),
    ] = None,
    write_mode: Annotated[
        str | None,
        typer.Option(
            help=(
                "Lakehouse write mode: append, overwrite, error, ignore, or create "
                "(Delta / Iceberg / DuckLake / Lance)."
            ),
        ),
    ] = None,
    row_group_size: Annotated[
        int | None,
        typer.Option(
            "--row-group-size",
            help=(
                "Parquet write row-group size (iterabledata row_group_size; "
                "defaults to the writer batch size when omitted). Skips DuckDB COPY."
            ),
        ),
    ] = None,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    use_totals: Annotated[
        bool,
        typer.Option(
            "--use-totals",
            help="Use format-reported row totals for convert progress when available.",
        ),
    ] = False,
    where: WhereOpt = None,
    add: AddOpt = None,
    partition_by: Annotated[
        str | None,
        typer.Option(
            "--partition-by",
            help="Write OUTPUT as a directory partitioned by these fields (Hive layout), "
            "e.g. year,month.",
        ),
    ] = None,
    max_open_files: MaxOpenFilesOpt = 128,
):
    """Convert one file (or a directory/glob with --recursive) to another format.

    Reading and writing are handled by the iterabledata engine, so any format it
    supports (100+ formats, including cloud URIs like s3://, gs://, az://) can be
    used as input or output. Use ``undatum formats list`` to see all formats.

    For multi-GB files, prefer ``--low-memory`` (uses DuckDB spill-to-disk when the
    format is duckable, and smaller Parquet write batches otherwise).

    Examples:
        # Single file
        undatum convert data.csv data.parquet

        # Large file, low memory
        undatum convert huge.jsonl.zst huge.parquet --low-memory

        # Bulk-convert a directory of CSVs to Parquet
        undatum convert ./raw ./processed --recursive --to-ext parquet

        # Bulk-convert with a glob pattern
        undatum convert "data/*.jsonl" ./out --recursive --to-ext csv

        # Custom bulk output names
        undatum convert ./raw ./out --recursive --to-ext jsonl --filename-pattern "{stem}.converted.jsonl"

        # CSV with a non-default quote character
        undatum convert data.csv out.jsonl --quotechar "'"

        # Named Excel sheet
        undatum convert workbook.xlsx out.jsonl --table Sheet2

        # Native batch Parquet with column projection
        undatum convert data.parquet out.parquet --native-batch --columns id,name

        # Codec profile on compressed output
        undatum convert data.csv data.csv.zst --profile max

        # Explicit compression level (overrides --profile)
        undatum convert data.csv data.csv.gz --level 9

        # Lakehouse write mode
        undatum convert data.parquet lake.delta --write-mode overwrite

        # Parquet row-group size (pair with --batch-size to split large write batches)
        undatum convert data.csv data.parquet --row-group-size 100000 --engine iterable

        # Progress using format-reported row totals
        undatum convert data.parquet out.jsonl --use-totals

        # Skip malformed JSONL rows instead of aborting
        undatum convert messy.jsonl clean.jsonl --on-error skip --error-log errors.jsonl

        # Parallel Python-engine convert (CPU-bound transforms / multi-core)
        undatum convert big.csv out.jsonl --engine python --threads 8
    """
    from ...cmds.converter import Converter

    if verbose:
        enable_verbose()
    options = {
        "where": where,
        "partition_by": partition_by,
        "max_open_files": max_open_files,
        "add": add,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "compression": compression,
        "flatten": flatten_data,
        "encoding": encoding,
        "prefix_strip": prefix_strip,
        "start_line": start_line,
        "start_page": start_page,
        "table": table,
        "tagname": tagname,
        "format_in": format_in,
        "format_out": format_out,
        "batch_size": batch_size,
        "scan_limit": scan_limit,
        "atomic": atomic,
        "threads": threads,
        "progress": progress,
        "low_memory": low_memory,
        "engine": engine,
        "profile": profile,
        "level": level,
        "native_batch": native_batch,
        "strict_native": strict_native,
        "columns": columns,
        "row_range": row_range,
        "write_mode": write_mode,
        "row_group_size": row_group_size,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "use_totals": use_totals,
        "filename_pattern": filename_pattern,
    }
    acmd = Converter(batch_size=batch_size)
    is_glob = any(ch in input_file for ch in "*?[")
    is_dir = os.path.isdir(input_file)
    if (is_dir or is_glob) and not recursive:
        raise ValidationError(
            "Bulk input detected (directory or glob pattern). Use --recursive to bulk-convert.",
            field="input",
        )
    if recursive:
        acmd.bulk_convert(input_file, output, options, to_ext=to_ext)
    else:
        acmd.convert(input_file, output, options, limit=scan_limit)


@data_app.command()
def repack(
    input_file: Annotated[str, typer.Argument(help="Path to input file to recompress.")],
    output: Annotated[
        str | None,
        typer.Argument(help="Output path (defaults to atomic in-place rewrite of INPUT)."),
    ] = None,
    level: Annotated[
        int | None,
        typer.Option(
            "--level",
            "-l",
            help="Compression level (overrides default maximum / max profile).",
        ),
    ] = None,
    compression: Annotated[
        str | None,
        typer.Option(
            help=(
                "Override compression codec. For container files: gz/zst/bz2/…. "
                "For Parquet/ORC/AVRO: format-native codec (e.g. zstd, snappy)."
            ),
        ),
    ] = None,
    progress: Annotated[bool, typer.Option(help="Show progress bar.")] = True,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Recompress a file at maximum compression by default.

    Container-compressed files (``.gz``, ``.zst``, ``.bz2``, …) are stream-recompressed
    with the same codec at max strength. Formats with built-in compression (Parquet,
    ORC, AVRO) are rewritten using native compression (Parquet defaults to ``zstd``).

    When OUTPUT is omitted, the input is replaced atomically after a successful write.

    Examples:
        undatum repack data.csv.gz
        undatum repack data.csv.gz data.csv.gz --level 6
        undatum repack data.parquet out.parquet
        undatum repack data.csv data.csv.zst
    """
    from ...cmds.repacker import Repacker

    if verbose:
        enable_verbose()
    options = {
        "level": level,
        "compression": compression,
        "progress": progress,
    }
    Repacker().repack(input_file, output, options)


@data_app.command()
def extract(
    input_files: Annotated[list[str], typer.Argument(help="Input file(s) to extract from.")],
    output_format: Annotated[
        str, typer.Option(help="Output format: csv, json, ndjson, parquet, datapackage.")
    ] = "csv",
    output: Annotated[
        str | None, typer.Option(help="Output file path (single table only).")
    ] = None,
    output_dir: Annotated[
        str | None, typer.Option(help="Output directory for multiple tables.")
    ] = None,
    method: Annotated[
        str | None, typer.Option(help="Extraction method: tables, text, ocr.")
    ] = None,
    pages: Annotated[
        str | None, typer.Option(help="PDF pages to extract (e.g., 1-3,7,10-12).")
    ] = None,
    ocr: Annotated[bool, typer.Option(help="Enable OCR for scanned PDFs.")] = False,
    flatten: Annotated[
        bool, typer.Option(help="Flatten multiple tables into one output table.")
    ] = False,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Extract tables or text from documents."""
    from ...cmds.extractor import Extractor

    if verbose:
        enable_verbose()
    options = {
        "output_format": output_format,
        "output": output,
        "output_dir": output_dir,
        "method": method,
        "pages": pages,
        "ocr": ocr,
        "flatten": flatten,
    }
    Extractor().extract(input_files, options)


@data_app.command()
def flatten(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = "utf8",
    format_in: Annotated[
        str, typer.Option(help="Override input file format detection (e.g., 'jsonl', 'xml').")
    ] = None,
    filter_expr: Annotated[
        str,
        typer.Option(
            "--filter",
            "--filter-expr",
            help="Filter expression to apply before flattening.",
        ),
    ] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
):
    """Flatten nested data records into one value per row.

    Converts nested structures (arrays, objects) into flat records.
    """
    from ...cmds.textproc import TextProcessor

    if verbose:
        enable_verbose()
    options = {
        "delimiter": delimiter,
        "quotechar": quotechar,
        "output": output,
        "encoding": encoding,
        "format_in": format_in,
        "filter": filter_expr,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
    }
    acmd = TextProcessor()
    acmd.flatten(input_file, options)


@data_app.command()
def split(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str,
        typer.Option(
            help="Optional output file path prefix. If not specified, uses input filename."
        ),
    ] = None,
    fields: Annotated[
        str,
        typer.Option(
            help="Comma-separated field names to split by (creates one file per unique value combination)."
        ),
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
    gzipfile: Annotated[str, typer.Option(help="Gzip compression option for output files.")] = None,
    chunksize: Annotated[
        int,
        typer.Option(help="Number of records per chunk when splitting by size (default: 10000)."),
    ] = 10000,
    filter_expr: Annotated[
        str,
        typer.Option(
            "--filter",
            "--filter-expr",
            help="Filter expression to apply before splitting.",
        ),
    ] = None,
    dirname: Annotated[str, typer.Option(help="Directory path to write output files to.")] = None,
    table: TableNameOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
    hive: Annotated[
        bool,
        typer.Option(
            "--hive", help="With --fields, write field=value directories (Hive partitioning)."
        ),
    ] = False,
    max_open_files: MaxOpenFilesOpt = 128,
    format_out: Annotated[
        str | None,
        typer.Option(
            "--format-out", "-O", help="Format of the parts (default: the input's format)."
        ),
    ] = None,
):
    """Split a data file into multiple chunks.

    Can split by chunk size or by unique field values.
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
        "format_in": format_in,
        "zipfile": zipfile,
        "gzipfile": gzipfile,
        "chunksize": chunksize,
        "filter": filter_expr,
        "dirname": dirname,
        "hive": hive,
        "max_open_files": max_open_files,
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
    acmd = Selector()
    acmd.split(input_file, options)


@data_app.command()
def fmt(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    delimiter: Annotated[str, typer.Option(help="CSV delimiter character (default: comma).")] = ",",
    quotechar: QuoteCharOpt = None,
    quote: Annotated[
        str,
        typer.Option(help="Quote style: 'minimal' (default), 'always', 'none', or 'nonnumeric'."),
    ] = "minimal",
    escape: Annotated[
        str, typer.Option(help="Escape character: 'double' (default), 'backslash', or 'none'.")
    ] = "double",
    line_ending: Annotated[
        str, typer.Option(help="Line ending: 'unix' (default), 'windows', 'crlf', or 'mac'.")
    ] = "unix",
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
    """Reformat CSV data with specific formatting options.

    Controls delimiter, quote style, escape character, and line endings.
    """
    from ...cmds.formatter import Formatter

    if verbose:
        enable_verbose()
    options = {
        "output": output,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "quote": quote,
        "escape": escape,
        "line_ending": line_ending,
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
    acmd = Formatter()
    acmd.fmt(input_file, options)
