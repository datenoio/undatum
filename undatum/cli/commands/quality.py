"""Validation."""

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
    TableNameOpt,
    TrustOpt,
)
from ._app import data_app


@data_app.command()
def validate(
    input_file: Annotated[
        str | None, typer.Argument(help="Path to input file (not needed with --list-rules).")
    ] = None,
    output: Annotated[
        str, typer.Option(help="Optional output file path. If not specified, prints to stdout.")
    ] = None,
    fields: Annotated[
        str, typer.Option(help="Comma-separated list of field names to validate (legacy mode).")
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
    rule: Annotated[
        str,
        typer.Option(
            help="Validation rule name (legacy mode, e.g., 'common.email', 'common.url')."
        ),
    ] = None,
    filter_expr: Annotated[
        str,
        typer.Option(
            "--filter",
            "--filter-expr",
            help="Filter expression to apply before validation.",
        ),
    ] = None,
    mode: Annotated[
        str,
        typer.Option(
            help="Legacy --rule output: 'invalid' (default), 'valid', 'all', or 'stats' (JSON counts)."
        ),
    ] = "invalid",
    rules: Annotated[
        str, typer.Option(help="Path to YAML/JSON rule file for rich validation.")
    ] = None,
    severity: Annotated[
        str,
        typer.Option(
            help="Filter violations by severity: 'error', 'warning', 'info', or 'all' (default)."
        ),
    ] = "all",
    output_format: Annotated[
        str, typer.Option(help="Output format: 'text' (default) or 'json'.")
    ] = "text",
    violation_report: Annotated[
        str, typer.Option(help="Path to write detailed violation report (JSON format).")
    ] = None,
    fail_on_warnings: Annotated[
        bool, typer.Option(help="Treat warnings as errors (exit with non-zero code).")
    ] = False,
    max_violations: Annotated[
        int,
        typer.Option(
            help="Maximum number of violations to display (default: 10 for text, 100 for JSON)."
        ),
    ] = None,
    progress: Annotated[bool, typer.Option(help="Show progress bar.")] = False,
    threads: Annotated[
        int,
        typer.Option(
            help=(
                "Worker processes for rule-file validation chunk parallelism. "
                "Omit for sequential processing."
            )
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
    json_output: JsonOpt = False,
    list_rules: Annotated[
        bool,
        typer.Option("--list-rules", help="List the built-in rules (format: ...) and exit."),
    ] = False,
):
    """Validate data against validation rules.

    Two modes:
    1. Rule file mode: Use --rules option with YAML/JSON rule file for rich validation
    2. Legacy mode: Use --fields and --rule options for simple single-rule validation

    Examples:
        # Rich validation with rule file
        undatum validate data.csv --rules validation-rules.yml

        # Parallel rule-file validation
        undatum validate data.csv --rules validation-rules.yml --threads 4

        # Legacy mode (backward compatible)
        undatum validate data.csv --fields email --rule common.email

        # Built-in rules for 'format:' in rule files
        undatum validate --list-rules
    """
    from ...cmds.validator import Validator

    if verbose:
        enable_verbose()
    if list_rules:
        from ...validate.library import print_catalogue

        print_catalogue("json" if json_output else output_format)
        return
    if not input_file:
        raise typer.BadParameter("INPUT_FILE is required (or use --list-rules)")

    if json_output:
        output_format = "json"
    # Set default max_violations based on output format
    if max_violations is None:
        max_violations = 100 if output_format == "json" else 10

    options = {
        "delimiter": delimiter,
        "quotechar": quotechar,
        "fields": fields,
        "output": output,
        "encoding": encoding,
        "format_in": format_in,
        "zipfile": zipfile,
        "filter": filter_expr,
        "rule": rule,
        "mode": mode,
        "rules": rules,
        "severity": severity,
        "output_format": "json" if json_output else output_format,
        "violation_report": violation_report,
        "fail_on_warnings": fail_on_warnings,
        "max_violations": max_violations,
        "progress": progress,
        "threads": threads,
        "table": table,
        "start_page": start_page,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }
    acmd = Validator()
    acmd.validate(input_file, options)


@data_app.command()
def quality(
    input_file: Annotated[str, typer.Argument(help="Path to input file.")],
    rules: Annotated[
        str | None, typer.Option("--rules", help="Validation rule file (YAML/JSON) to apply.")
    ] = None,
    schema: Annotated[
        str | None,
        typer.Option(
            "--schema",
            help="Expected schema: `undatum schema --json` output, JSON Schema, Frictionless "
            "schema or a reference data file.",
        ),
    ] = None,
    thresholds: Annotated[
        str | None,
        typer.Option(
            "--thresholds", help="Thresholds file (YAML/JSON); a failed one exits with 1."
        ),
    ] = None,
    format_out: Annotated[
        str | None,
        typer.Option("--format-out", "-O", help="Report format: markdown (default), html, json."),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Write the report here (format from the extension)."),
    ] = None,
    format_in: Annotated[
        str | None, typer.Option("--format-in", "-F", help="Override input format detection.")
    ] = None,
    table: TableNameOpt = None,
    json_output: JsonOpt = False,
):
    """Report whether a dataset is fit for use, and exit with 1 when a threshold fails.

    Profiles every field (empty values, distinct values, top values, type conformance),
    compares the schema with --schema, applies --rules, and checks --thresholds.

    Examples:
        undatum quality data.csv
        undatum quality data.csv --rules rules.yml --thresholds quality.yml -o report.html
        undatum quality data.csv --schema expected.json --json
    """
    from ...cmds.quality import build_report, write_report

    report = build_report(
        input_file,
        rules=rules,
        schema=schema,
        thresholds=thresholds,
        options={"format_in": format_in, "table": table},
    )
    write_report(report, "json" if json_output else format_out, output)
    if not report["verdict"]["passed"]:
        raise typer.Exit(1)
