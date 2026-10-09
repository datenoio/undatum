"""CLI commands for Frictionless Data Package generation."""

from typing import Annotated

import typer

from .common import AI_PROVIDER_HELP, AIMaskSamplesOpt, build_ai_config, enable_verbose

package_app = typer.Typer(help="Frictionless Data Package commands.")


def _build_package_options(
    *,
    output: str | None = None,
    package_dir: str | None = None,
    name: str | None = None,
    title: str | None = None,
    description: str | None = None,
    keywords: str | None = None,
    licenses: str | None = None,
    sources: str | None = None,
    contributors: str | None = None,
    version: str | None = None,
    sample_size: int = 10,
    objects_limit: int = 10000,
    engine: str | None = None,
    delimiter: str | None = None,
    quotechar: str | None = None,
    encoding: str | None = None,
    tagname: str | None = None,
    start_line: int = 0,
    start_page: int = 0,
    format_in: str | None = None,
    autodoc: bool = False,
    lang: str = "English",
    ai_provider: str | None = None,
    ai_model: str | None = None,
    ai_base_url: str | None = None,
    pii_mask_samples: bool | None = None,
    zip_output: str | None = None,
    quiet: bool = False,
    table: str | None = None,
    trust: bool = False,
    on_error: str | None = None,
    error_log: str | None = None,
    flatten_nested: bool = False,
    max_nested_depth: int | None = None,
    keep_nested_parents: bool = True,
) -> dict:
    ai_config = build_ai_config(ai_model, ai_base_url, pii_mask_samples)

    return {
        "output": output,
        "package_dir": package_dir,
        "name": name,
        "title": title,
        "description": description,
        "keywords": keywords,
        "licenses": licenses,
        "sources": sources,
        "contributors": contributors,
        "version": version,
        "sample_size": sample_size,
        "objects_limit": objects_limit,
        "engine": engine,
        "delimiter": delimiter,
        "quotechar": quotechar,
        "encoding": encoding,
        "tagname": tagname,
        "start_line": start_line,
        "start_page": start_page,
        "format_in": format_in,
        "autodoc": autodoc,
        "lang": lang,
        "ai_provider": ai_provider,
        "ai_config": ai_config,
        "zip": zip_output,
        "quiet": quiet,
        "table": table,
        "trust": trust,
        "on_error": on_error,
        "error_log": error_log,
        "flatten_nested": flatten_nested,
        "max_nested_depth": max_nested_depth,
        "keep_nested_parents": keep_nested_parents,
    }


@package_app.command("create")
def package_create(
    input_files: Annotated[list[str], typer.Argument(help="Input file(s) to package.")],
    output: Annotated[str | None, typer.Option(help="Output datapackage.json path.")] = None,
    package_dir: Annotated[
        str | None, typer.Option(help="Package directory to materialize.")
    ] = None,
    name: Annotated[str | None, typer.Option(help="Package name (slug).")] = None,
    title: Annotated[str | None, typer.Option(help="Package title.")] = None,
    description: Annotated[str | None, typer.Option(help="Package description.")] = None,
    keywords: Annotated[str | None, typer.Option(help="Comma-separated keywords.")] = None,
    licenses: Annotated[
        str | None,
        typer.Option(
            help="Licenses (semicolon-separated entries, e.g. 'name=MIT;name=ODC-PDDL-1.0')."
        ),
    ] = None,
    sources: Annotated[
        str | None,
        typer.Option(
            help="Sources (semicolon-separated entries, e.g. 'title=World Bank,path=https://...')."
        ),
    ] = None,
    contributors: Annotated[
        str | None,
        typer.Option(
            help="Contributors (semicolon-separated entries, e.g. 'title=Jane Doe,email=jane@example.com')."
        ),
    ] = None,
    version: Annotated[str | None, typer.Option(help="Package version string.")] = None,
    sample_size: Annotated[
        int, typer.Option(help="Number of sample records to include in metadata inference.")
    ] = 10,
    objects_limit: Annotated[
        int, typer.Option(help="Maximum number of objects to analyze for schema inference.")
    ] = 10000,
    engine: Annotated[
        str | None,
        typer.Option(help="Processing engine: 'auto' (default) or 'duckdb'."),
    ] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: Annotated[
        str | None,
        typer.Option(
            "--quotechar",
            help="CSV quote character (iterabledata default '\"' when omitted).",
        ),
    ] = None,
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
    format_in: Annotated[
        str | None,
        typer.Option(help="Override input file format detection (e.g., 'csv', 'jsonl', 'xml')."),
    ] = None,
    autodoc: Annotated[bool, typer.Option(help="Enable AI-powered metadata generation.")] = False,
    lang: Annotated[
        str, typer.Option(help="Language for AI-generated metadata (default: 'English').")
    ] = "English",
    ai_provider: Annotated[
        str | None,
        typer.Option(help=AI_PROVIDER_HELP),
    ] = None,
    ai_model: Annotated[
        str | None, typer.Option(help="Model name to use (provider-specific).")
    ] = None,
    ai_base_url: Annotated[str | None, typer.Option(help="Base URL for AI API (optional).")] = None,
    pii_mask_samples: AIMaskSamplesOpt = None,
    zip_output: Annotated[
        str | None,
        typer.Option(
            "--zip",
            help="Create a ZIP archive of the package directory (requires --package-dir).",
        ),
    ] = None,
    table: Annotated[
        str | None,
        typer.Option(
            "--table",
            "--sheet",
            help="Table or sheet name for multi-table sources (Excel, SQLite, lakehouse).",
        ),
    ] = None,
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
    """Generate a Frictionless Data Package descriptor."""
    from ..cmds.packager import Packager

    if verbose:
        enable_verbose()

    options = _build_package_options(
        output=output,
        package_dir=package_dir,
        name=name,
        title=title,
        description=description,
        keywords=keywords,
        licenses=licenses,
        sources=sources,
        contributors=contributors,
        version=version,
        sample_size=sample_size,
        objects_limit=objects_limit,
        engine=engine,
        delimiter=delimiter,
        quotechar=quotechar,
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
        pii_mask_samples=pii_mask_samples,
        zip_output=zip_output,
        table=table,
        trust=trust,
        on_error=on_error,
        error_log=error_log,
        flatten_nested=flatten_nested,
        max_nested_depth=max_nested_depth,
        keep_nested_parents=keep_nested_parents,
    )
    Packager().create(input_files, options)


@package_app.command("add-resource")
def package_add_resource(
    package_file: Annotated[str, typer.Argument(help="Existing datapackage.json to extend.")],
    input_files: Annotated[list[str], typer.Argument(help="Input file(s) to add.")],
    package_dir: Annotated[
        str | None,
        typer.Option(help="Package directory containing data files (defaults to descriptor dir)."),
    ] = None,
    sample_size: Annotated[int, typer.Option(help="Sample size for metadata inference.")] = 10,
    objects_limit: Annotated[int, typer.Option(help="Maximum objects to analyze.")] = 10000,
    engine: Annotated[str | None, typer.Option(help="Processing engine.")] = None,
    delimiter: Annotated[
        str | None, typer.Option(help="CSV delimiter character (auto-detected when omitted).")
    ] = None,
    quotechar: Annotated[
        str | None,
        typer.Option(
            "--quotechar",
            help="CSV quote character (iterabledata default '\"' when omitted).",
        ),
    ] = None,
    encoding: Annotated[str | None, typer.Option(help="File encoding.")] = None,
    tagname: Annotated[str | None, typer.Option(help="XML record tag name.")] = None,
    start_line: Annotated[
        int, typer.Option(help="Line number (0-based) to start reading from.")
    ] = 0,
    start_page: Annotated[int, typer.Option(help="Excel start page (0-based).")] = 0,
    format_in: Annotated[str | None, typer.Option(help="Override input format.")] = None,
    autodoc: Annotated[bool, typer.Option(help="Enable AI-powered metadata generation.")] = False,
    lang: Annotated[str, typer.Option(help="Language for AI metadata.")] = "English",
    ai_provider: Annotated[str | None, typer.Option(help=AI_PROVIDER_HELP)] = None,
    ai_model: Annotated[str | None, typer.Option(help="AI model name.")] = None,
    ai_base_url: Annotated[str | None, typer.Option(help="AI API base URL.")] = None,
    pii_mask_samples: AIMaskSamplesOpt = None,
    table: Annotated[
        str | None,
        typer.Option(
            "--table",
            "--sheet",
            help="Table or sheet name for multi-table sources (Excel, SQLite, lakehouse).",
        ),
    ] = None,
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
    """Add resources to an existing Frictionless Data Package descriptor."""
    from ..cmds.packager import Packager

    if verbose:
        enable_verbose()

    options = _build_package_options(
        package_dir=package_dir,
        sample_size=sample_size,
        objects_limit=objects_limit,
        engine=engine,
        delimiter=delimiter,
        quotechar=quotechar,
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
        pii_mask_samples=pii_mask_samples,
        table=table,
        trust=trust,
        on_error=on_error,
        error_log=error_log,
        flatten_nested=flatten_nested,
        max_nested_depth=max_nested_depth,
        keep_nested_parents=keep_nested_parents,
    )
    Packager().add_resource(package_file, input_files, options)


@package_app.command("validate")
def package_validate(
    package_file: Annotated[str, typer.Argument(help="Path to datapackage.json.")],
    limit_rows: Annotated[
        int | None, typer.Option(help="Limit rows validated per resource.")
    ] = None,
    check_data: Annotated[
        bool, typer.Option(help="Validate resource data in addition to metadata.")
    ] = True,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Validate a Frictionless Data Package descriptor."""
    from ..cmds.packager import Packager

    if verbose:
        enable_verbose()

    options = {
        "limit_rows": limit_rows,
        "check_data": check_data,
        "quiet": False,
    }
    Packager().validate(package_file, options)
