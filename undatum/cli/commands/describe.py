"""Schemas, analysis reports and dataset documentation (with optional AI help)."""

from typing import Annotated

import typer

from ..common import AI_PROVIDER_HELP, AIMaskSamplesOpt, build_ai_config, enable_verbose
from ..options import (
    DocMaskSamplesOpt,
    ErrorLogOpt,
    FlattenNestedOpt,
    JsonOpt,
    KeepNestedParentsOpt,
    MaxNestedDepthOpt,
    OnErrorOpt,
    QuoteCharOpt,
    TableNameOpt,
    TrustOpt,
)
from ._app import data_app


@data_app.command()
def scheme(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
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
    stype: Annotated[
        str, typer.Option(help="Schema type: 'cerberus' (default) or other schema formats.")
    ] = "cerberus",
):
    """[DEPRECATED] Generate data schema from file.

    ⚠️  This command is deprecated. Use 'undatum schema --format cerberus' instead.

    Creates a schema definition based on the structure of the input data.
    This command will be removed in a future version.
    """
    import warnings

    from ...cmds.schemer import Schemer

    warnings.warn(
        "The 'scheme' command is deprecated. Use 'undatum schema --format cerberus' instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    if verbose:
        enable_verbose()

    # Redirect to schema command with cerberus format
    # Build AI configuration (not used for scheme, but needed for schema command)
    options = {
        "outtype": "json",  # Cerberus format outputs JSON
        "format": "cerberus",
        "output": output,
        "autodoc": False,
        "engine": "auto",
    }
    acmd = Schemer()
    acmd.extract_schema(input_file, options)


@data_app.command()
def analyze(
    input_file: Annotated[str, typer.Argument(help="Path to input file to analyze.")],
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default), 'duckdb', or 'iterable'."),
    ] = None,
    use_pandas: Annotated[
        bool, typer.Option(help="Use pandas for data processing (may use more memory).")
    ] = False,
    outtype: Annotated[
        str,
        typer.Option(help="Output format: 'text' (default), 'json', 'yaml', or 'markdown'."),
    ] = None,
    format_out: Annotated[
        str,
        typer.Option(
            help="Alias for --outtype. Also inferred from --output (.json/.yaml/.yml/.md)."
        ),
    ] = None,
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    autodoc: Annotated[
        bool, typer.Option(help="Enable AI-powered automatic field and dataset documentation.")
    ] = False,
    lang: Annotated[
        str, typer.Option(help="Language for AI-generated documentation (default: 'English').")
    ] = "English",
    ai_provider: Annotated[
        str,
        typer.Option(help=AI_PROVIDER_HELP),
    ] = None,
    ai_model: Annotated[
        str,
        typer.Option(help="Model name to use (provider-specific, e.g., 'gpt-4o-mini' for OpenAI)."),
    ] = None,
    ai_base_url: Annotated[
        str,
        typer.Option(
            help="Base URL for AI API (optional, uses provider-specific defaults if not specified)."
        ),
    ] = None,
    pii_mask_samples: AIMaskSamplesOpt = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[str, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")] = None,
    objects_limit: Annotated[
        int, typer.Option(help="Maximum number of records to scan for schema inference.")
    ] = 10000,
    ignore_errors: Annotated[
        bool, typer.Option(help="Ignore parse errors in CSV/JSON files (default: True).")
    ] = True,
    no_scan: Annotated[
        bool, typer.Option(help="Return file metadata only; skip structure scan.")
    ] = False,
    no_stats: Annotated[
        bool, typer.Option(help="Skip uniqueness statistics in field analysis.")
    ] = False,
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
    """Analyzes given data file and returns human readable insights.

    Provides detailed analysis of file structure, encoding, fields, data types,
    and optionally AI-generated field descriptions and dataset summaries.
    """
    from ...cmds.analyzer import Analyzer

    if verbose:
        enable_verbose()

    ai_config = build_ai_config(ai_model, ai_base_url, pii_mask_samples)

    options = {
        "engine": engine,
        "use_pandas": use_pandas,
        "outtype": outtype,
        "format_out": "json" if json_output else format_out,
        "output": output,
        "autodoc": autodoc,
        "lang": lang,
        "ai_provider": ai_provider,
        "ai_config": ai_config,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "objects_limit": objects_limit,
        "ignore_errors": ignore_errors,
        "scan": not no_scan,
        "stats": not no_stats,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Analyzer()
    acmd.analyze(input_file, options)


def _run_doc_command(
    input_file: str,
    format: str,
    output: str | None,
    sample_size: int,
    verbose: bool,
    engine: str,
    delimiter: str,
    encoding: str | None,
    tagname: str | None,
    start_line: int,
    start_page: int,
    format_in: str | None,
    autodoc: bool,
    lang: str,
    ai_provider: str | None,
    ai_model: str | None,
    ai_base_url: str | None,
    semantic_types: bool,
    pii_detect: bool,
    pii_mask_samples: bool | None,
    table: str | None = None,
    trust: bool = False,
    on_error: str | None = None,
    error_log: str | None = None,
    quotechar: str | None = None,
    flatten_nested: bool = False,
    max_nested_depth: int | None = None,
    keep_nested_parents: bool = True,
):
    from ...cmds.doc import Documenter

    if verbose:
        enable_verbose()

    ai_config = build_ai_config(ai_model, ai_base_url, pii_mask_samples)

    options = {
        "format": format,
        "output": output,
        "sample_size": sample_size,
        "engine": engine,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "tagname": tagname,
        "start_line": start_line,
        "start_page": start_page,
        "format_in": format_in,
        "table": table,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "autodoc": autodoc,
        "lang": lang,
        "ai_provider": ai_provider,
        "ai_config": ai_config,
        "semantic_types": semantic_types,
        "pii_detect": pii_detect,
        "pii_mask_samples": bool(pii_mask_samples),
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Documenter()
    acmd.document(input_file, options)


@data_app.command()
def doc(
    input_file: Annotated[str, typer.Argument(help="Path to input file to document.")],
    format: Annotated[
        str, typer.Option(help="Output format: 'markdown' (default), 'json', 'yaml', or 'text'.")
    ] = "markdown",
    output: Annotated[
        str | None,
        typer.Option(help="Optional output file path. If not specified, prints to stdout."),
    ] = None,
    sample_size: Annotated[
        int, typer.Option(help="Number of sample records to include (default: 10).")
    ] = 10,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default) or 'duckdb'."),
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[
        str | None, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")
    ] = None,
    tagname: Annotated[
        str | None, typer.Option(help="XML tag name that contains individual records.")
    ] = None,
    start_line: Annotated[
        int, typer.Option(help="Line number (0-based) to start reading from.")
    ] = 0,
    start_page: Annotated[
        int, typer.Option(help="Page number (0-based) to start from for Excel files.")
    ] = 0,
    table: TableNameOpt = None,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    format_in: Annotated[
        str | None,
        typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl')."),
    ] = None,
    autodoc: Annotated[
        bool, typer.Option(help="Enable AI-powered automatic field and dataset documentation.")
    ] = False,
    lang: Annotated[
        str, typer.Option(help="Language for AI-generated documentation (default: 'English').")
    ] = "English",
    ai_provider: Annotated[
        str | None,
        typer.Option(help=AI_PROVIDER_HELP),
    ] = None,
    ai_model: Annotated[
        str | None,
        typer.Option(help="Model name to use (provider-specific, e.g., 'gpt-4o-mini' for OpenAI)."),
    ] = None,
    ai_base_url: Annotated[
        str | None,
        typer.Option(
            help="Base URL for AI API (optional, uses provider-specific defaults if not specified)."
        ),
    ] = None,
    semantic_types: Annotated[
        bool, typer.Option(help="Enable semantic type annotations using Metacrafter.")
    ] = False,
    pii_detect: Annotated[
        bool, typer.Option(help="Enable PII detection using Metacrafter.")
    ] = False,
    pii_mask_samples: DocMaskSamplesOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Generate documentation for a dataset."""
    _run_doc_command(
        input_file=input_file,
        format=format,
        output=output,
        sample_size=sample_size,
        verbose=verbose,
        engine=engine,
        delimiter=delimiter,
        encoding=encoding,
        tagname=tagname,
        start_line=start_line,
        start_page=start_page,
        format_in=format_in,
        autodoc=autodoc,
        lang=lang,
        ai_provider=ai_provider,
        ai_model=ai_model,
        ai_base_url=ai_base_url,
        semantic_types=semantic_types,
        pii_detect=pii_detect,
        pii_mask_samples=pii_mask_samples,
        table=table,
        trust=trust,
        on_error=on_error,
        error_log=error_log,
        quotechar=quotechar,
        flatten_nested=flatten_nested,
        max_nested_depth=max_nested_depth,
        keep_nested_parents=keep_nested_parents,
    )


@data_app.command()
def document(
    input_file: Annotated[str, typer.Argument(help="Path to input file to document.")],
    format: Annotated[
        str, typer.Option(help="Output format: 'markdown' (default), 'json', 'yaml', or 'text'.")
    ] = "markdown",
    output: Annotated[
        str | None,
        typer.Option(help="Optional output file path. If not specified, prints to stdout."),
    ] = None,
    sample_size: Annotated[
        int, typer.Option(help="Number of sample records to include (default: 10).")
    ] = 10,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default) or 'duckdb'."),
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: QuoteCharOpt = None,
    encoding: Annotated[
        str | None, typer.Option(help="File encoding (e.g., 'utf8', 'latin1').")
    ] = None,
    tagname: Annotated[
        str | None, typer.Option(help="XML tag name that contains individual records.")
    ] = None,
    start_line: Annotated[
        int, typer.Option(help="Line number (0-based) to start reading from.")
    ] = 0,
    start_page: Annotated[
        int, typer.Option(help="Page number (0-based) to start from for Excel files.")
    ] = 0,
    table: TableNameOpt = None,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    format_in: Annotated[
        str | None,
        typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl')."),
    ] = None,
    autodoc: Annotated[
        bool, typer.Option(help="Enable AI-powered automatic field and dataset documentation.")
    ] = False,
    lang: Annotated[
        str, typer.Option(help="Language for AI-generated documentation (default: 'English').")
    ] = "English",
    ai_provider: Annotated[
        str | None,
        typer.Option(help=AI_PROVIDER_HELP),
    ] = None,
    ai_model: Annotated[
        str | None,
        typer.Option(help="Model name to use (provider-specific, e.g., 'gpt-4o-mini' for OpenAI)."),
    ] = None,
    ai_base_url: Annotated[
        str | None,
        typer.Option(
            help="Base URL for AI API (optional, uses provider-specific defaults if not specified)."
        ),
    ] = None,
    semantic_types: Annotated[
        bool, typer.Option(help="Enable semantic type annotations using Metacrafter.")
    ] = False,
    pii_detect: Annotated[
        bool, typer.Option(help="Enable PII detection using Metacrafter.")
    ] = False,
    pii_mask_samples: DocMaskSamplesOpt = None,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = True,
):
    """Generate documentation for a dataset (alias for doc)."""
    _run_doc_command(
        input_file=input_file,
        format=format,
        output=output,
        sample_size=sample_size,
        verbose=verbose,
        engine=engine,
        delimiter=delimiter,
        encoding=encoding,
        tagname=tagname,
        start_line=start_line,
        start_page=start_page,
        format_in=format_in,
        autodoc=autodoc,
        lang=lang,
        ai_provider=ai_provider,
        ai_model=ai_model,
        ai_base_url=ai_base_url,
        semantic_types=semantic_types,
        pii_detect=pii_detect,
        pii_mask_samples=pii_mask_samples,
        table=table,
        trust=trust,
        on_error=on_error,
        error_log=error_log,
        quotechar=quotechar,
        flatten_nested=flatten_nested,
        max_nested_depth=max_nested_depth,
        keep_nested_parents=keep_nested_parents,
    )


@data_app.command()
def schema(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    outtype: Annotated[
        str, typer.Option(help="Output format: 'text' (default), 'json', or 'yaml'.")
    ] = "text",
    format: Annotated[
        str,
        typer.Option(
            help="Schema format: 'yaml' (default), 'json', 'cerberus', 'jsonschema', 'avro', or 'parquet'. Overrides outtype when specified."
        ),
    ] = None,
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    autodoc: Annotated[
        bool, typer.Option(help="Enable AI-powered automatic field documentation.")
    ] = False,
    lang: Annotated[
        str, typer.Option(help="Language for AI-generated documentation (default: 'English').")
    ] = "English",
    ai_provider: Annotated[
        str,
        typer.Option(help=AI_PROVIDER_HELP),
    ] = None,
    ai_model: Annotated[
        str,
        typer.Option(help="Model name to use (provider-specific, e.g., 'gpt-4o-mini' for OpenAI)."),
    ] = None,
    ai_base_url: Annotated[
        str,
        typer.Option(
            help="Base URL for AI API (optional, uses provider-specific defaults if not specified)."
        ),
    ] = None,
    pii_mask_samples: AIMaskSamplesOpt = None,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default), 'duckdb', or 'iterable'."),
    ] = None,
    table: TableNameOpt = None,
    quotechar: QuoteCharOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    flatten_nested: FlattenNestedOpt = False,
    max_nested_depth: MaxNestedDepthOpt = None,
    keep_nested_parents: KeepNestedParentsOpt = False,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
    validate_schema: Annotated[
        bool,
        typer.Option(
            "--validate",
            help=(
                "Validate rows against an inferred schema (iterabledata schema.validate). "
                "Use `undatum validate` for rule packs."
            ),
        ),
    ] = False,
    strict: Annotated[
        bool,
        typer.Option(
            "--strict",
            help="With --validate, flag extra fields not present in the inferred schema.",
        ),
    ] = False,
    sample_size: Annotated[
        int | None,
        typer.Option(
            "--sample-size",
            help="With --validate, rows to sample when inferring the schema (engine default 10000).",
        ),
    ] = None,
    json_output: JsonOpt = False,
):
    """Extract schema from a data file.

    Generates a schema definition describing the structure and types of fields in the data.
    Supports multiple output formats including YAML, JSON, Cerberus, JSON Schema, Avro, and Parquet.
    Use ``--validate`` to check rows against the inferred schema (not rule-pack validation).
    """
    from ...cmds.schemer import Schemer

    if verbose:
        enable_verbose()

    ai_config = build_ai_config(ai_model, ai_base_url, pii_mask_samples)

    options = {
        "outtype": "json" if json_output else outtype,
        "format": format,
        "output": output,
        "autodoc": autodoc,
        "lang": lang,
        "ai_provider": ai_provider,
        "ai_config": ai_config,
        "engine": engine,
        "table": table,
        "quotechar": quotechar,
        "start_page": start_page,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "validate": validate_schema,
        "strict": strict,
        "sample_size": sample_size,
    }
    acmd = Schemer()
    result = acmd.extract_schema(input_file, options)
    if validate_schema and isinstance(result, dict) and not result.get("valid"):
        raise typer.Exit(code=1)


@data_app.command()
def schema_bulk(
    input_file: Annotated[
        str,
        typer.Argument(
            help="Glob pattern or directory path for input files (e.g., 'data/*.csv' or 'data/')."
        ),
    ],
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
    outtype: Annotated[
        str, typer.Option(help="Output format: 'text' (default), 'json', or 'yaml'.")
    ] = "text",
    format: Annotated[
        str,
        typer.Option(
            help="Schema format: 'yaml' (default), 'json', 'cerberus', 'jsonschema', 'avro', or 'parquet'. Overrides outtype when specified."
        ),
    ] = None,
    output: Annotated[str, typer.Option(help="Output directory path for schema files.")] = None,
    mode: Annotated[
        str,
        typer.Option(
            help="Extraction mode: 'distinct' (extract unique schemas, default) or 'perfile' (one schema per file)."
        ),
    ] = "distinct",
    autodoc: Annotated[
        bool, typer.Option(help="Enable AI-powered automatic field documentation.")
    ] = False,
    lang: Annotated[
        str, typer.Option(help="Language for AI-generated documentation (default: 'English').")
    ] = "English",
    ai_provider: Annotated[
        str,
        typer.Option(help=AI_PROVIDER_HELP),
    ] = None,
    ai_model: Annotated[
        str,
        typer.Option(help="Model name to use (provider-specific, e.g., 'gpt-4o-mini' for OpenAI)."),
    ] = None,
    ai_base_url: Annotated[
        str,
        typer.Option(
            help="Base URL for AI API (optional, uses provider-specific defaults if not specified)."
        ),
    ] = None,
    pii_mask_samples: AIMaskSamplesOpt = None,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default), 'duckdb', or 'iterable'."),
    ] = None,
    table: TableNameOpt = None,
    quotechar: QuoteCharOpt = None,
    start_page: Annotated[int, typer.Option(help="Sheet index (0-based) for Excel files.")] = 0,
    trust: TrustOpt = False,
    on_error: OnErrorOpt = None,
    error_log: ErrorLogOpt = None,
):
    """Extract schemas from multiple files.

    Processes multiple files and extracts their schemas, either as distinct unique schemas
    or one schema per file.
    """
    from ...cmds.schemer import Schemer

    if verbose:
        enable_verbose()

    ai_config = build_ai_config(ai_model, ai_base_url, pii_mask_samples)

    options = {
        "outtype": outtype,
        "format": format,
        "output": output,
        "mode": mode,
        "autodoc": autodoc,
        "lang": lang,
        "ai_provider": ai_provider,
        "ai_config": ai_config,
        "engine": engine,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "quotechar": quotechar,
    }
    acmd = Schemer()
    acmd.extract_schema_bulk(input_file, options)


@data_app.command("schema-drift")
def schema_drift(
    paths: Annotated[
        list[str], typer.Argument(help="Files, directories or glob patterns to check.")
    ],
    baseline: Annotated[
        str | None,
        typer.Option(
            "--baseline",
            help="Baseline: a data file, `undatum schema --json` output, JSON Schema or "
            "Frictionless schema (default: the first file).",
        ),
    ] = None,
    fail_on: Annotated[
        str | None,
        typer.Option(
            "--fail-on",
            help="Exit with 1 on these changes: added, removed, type, nullability, any.",
        ),
    ] = None,
    format_out: Annotated[
        str | None,
        typer.Option("--format-out", "-O", help="Report format: text (default), markdown, json."),
    ] = None,
    output: Annotated[
        str | None, typer.Option("--output", "-o", help="Write the report to this file.")
    ] = None,
    table: TableNameOpt = None,
    json_output: JsonOpt = False,
):
    """Compare the schema of every file with a baseline and report drift.

    Added, removed, retyped and nullability-changed fields, and likely renames, per file.

    Examples:
        undatum schema-drift deliveries/ --baseline schema.json --fail-on removed,type
        undatum schema-drift "exports/*.csv" -O markdown -o drift.md
    """
    from ...cmds.drift import emit_report, parse_fail_on, run_drift

    fail = parse_fail_on(fail_on)
    reference, diffs = run_drift(paths, baseline, {"table": table})
    emit_report(diffs, "json" if json_output else format_out, output, baseline=reference)
    if any(diff.fails(fail) for diff in diffs):
        raise typer.Exit(1)
