"""CLI commands for pipeline workflows and templates."""

import logging
import sys
from typing import Annotated

import typer

from ..common.errors import UndatumError, ValidationError
from .common import console, enable_verbose

logger = logging.getLogger(__name__)

pipeline_app = typer.Typer(help="Pipeline workflow commands.")
templates_app = typer.Typer(help="Pipeline template commands.")
pipeline_app.add_typer(templates_app, name="templates")


@pipeline_app.command()
def run(
    pipeline_file: Annotated[
        str, typer.Argument(help="Path to pipeline specification file (YAML or JSON).")
    ],
    var: Annotated[
        list[str] | None,
        typer.Option(help="Variable overrides in format key=value (can be used multiple times)."),
    ] = None,
    dry_run: Annotated[bool, typer.Option(help="Validate pipeline without executing.")] = False,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Execute a pipeline workflow from a YAML or JSON specification.

    Examples:
        # Run pipeline
        undatum pipeline run pipeline.yml

        # Run with variable overrides
        undatum pipeline run pipeline.yml --var input_bucket=my-bucket --var output_dir=/tmp

        # Validate without executing
        undatum pipeline run pipeline.yml --dry-run
    """
    from ..cmds.pipeline import PipelineRunner
    from ..common.pipeline_parser import PipelineParseError, parse_pipeline

    if verbose:
        enable_verbose()

    # Parse variable overrides
    variables = {}
    if var:
        for v in var:
            if "=" not in v:
                logger.error(f"Invalid variable format: {v}. Use key=value format.")
                sys.exit(1)
            key, value = v.split("=", 1)
            variables[key.strip()] = value.strip()

    try:
        # Parse pipeline
        spec = parse_pipeline(pipeline_file)

        # Run pipeline
        runner = PipelineRunner(dry_run=dry_run)
        success = runner.run(spec, variables=variables)

        if not success:
            sys.exit(1)

    except PipelineParseError as e:
        logger.error(f"Pipeline parsing error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline execution error: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@pipeline_app.command(name="validate")
def pipeline_validate(
    pipeline_file: Annotated[
        str, typer.Argument(help="Path to pipeline specification file (YAML or JSON).")
    ],
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Validate a pipeline specification without executing it.

    Checks that:
    - Pipeline file is valid YAML/JSON
    - All steps have required fields (name, command, args)
    - All commands are valid undatum commands
    - Variable references are properly formatted

    Examples:
        # Validate pipeline
        undatum pipeline validate pipeline.yml
    """
    from ..common.pipeline_parser import PipelineParseError, parse_pipeline, validate_pipeline

    if verbose:
        enable_verbose()

    try:
        # Parse pipeline
        spec = parse_pipeline(pipeline_file)

        # Validate
        errors = validate_pipeline(spec)

        if errors:
            logger.error("Pipeline validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            sys.exit(1)
        else:
            console.print("[green]Pipeline specification is valid[/green]")

    except PipelineParseError as e:
        logger.error(f"Pipeline parsing error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline validation error: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


@pipeline_app.command(name="doc")
def pipeline_doc(
    pipeline_file: Annotated[
        str, typer.Argument(help="Path to pipeline specification file (YAML or JSON).")
    ],
    output: Annotated[
        str | None,
        typer.Option(help="Write documentation to this path instead of stdout."),
    ] = None,
    format: Annotated[
        str,
        typer.Option(help="Output format: 'markdown' (default) or 'mermaid'."),
    ] = "markdown",
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Generate Mermaid documentation for a pipeline specification.

    Examples:
        undatum pipeline doc pipeline.yml
        undatum pipeline doc pipeline.yml --format mermaid --output flow.mmd
    """
    from ..common.pipeline_parser import (
        PipelineParseError,
        parse_pipeline,
        render_pipeline_markdown,
        render_pipeline_mermaid,
    )

    if verbose:
        enable_verbose()

    fmt = (format or "markdown").lower().strip()
    if output:
        lower = str(output).lower()
        if fmt == "markdown" and lower.endswith((".mmd", ".mermaid")):
            fmt = "mermaid"

    try:
        spec = parse_pipeline(pipeline_file)
    except PipelineParseError as e:
        raise ValidationError(str(e)) from e

    if fmt == "mermaid":
        text = render_pipeline_mermaid(spec)
    elif fmt in {"markdown", "md"}:
        text = render_pipeline_markdown(spec, source=pipeline_file)
    else:
        raise ValidationError("Unsupported pipeline doc format. Use 'markdown' or 'mermaid'.")

    if output:
        with open(output, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        typer.echo(text, nl=False)


@templates_app.command(name="list")
def templates_list(
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """List available pipeline templates.

    Examples:
        undatum pipeline templates list
    """
    from rich import print as rich_print
    from rich.table import Table

    from ..cmds.pipeline_templates import TemplateManager

    if verbose:
        enable_verbose()

    manager = TemplateManager()
    templates = manager.list_templates()

    if not templates:
        rich_print("[yellow]No pipeline templates found.[/yellow]")
        return

    table = Table(title="Pipeline Templates")
    table.add_column("Name", justify="left", style="magenta")
    table.add_column("Description", justify="left", style="cyan")
    table.add_column("Variables", justify="left", style="cyan")
    for tpl in templates:
        variables = ", ".join(v["name"] for v in tpl.get("variables", [])) or "-"
        table.add_row(tpl["name"], tpl.get("description", ""), variables)
    rich_print(table)


@templates_app.command(name="init")
def templates_init(
    template_name: Annotated[
        str,
        typer.Argument(help="Name of the template to initialize (see 'pipeline templates list')."),
    ],
    output: Annotated[str, typer.Option(help="Path to output pipeline file.")] = "pipeline.yml",
    var: Annotated[
        list[str] | None,
        typer.Option(help="Variable values in format key=value (can be used multiple times)."),
    ] = None,
    interactive: Annotated[
        bool,
        typer.Option(help="Prompt for missing variables (only when stdin is a terminal)."),
    ] = True,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Initialize a pipeline file from a template.

    Examples:
        # Initialize interactively
        undatum pipeline templates init basic-cleaning --output my-pipeline.yml

        # Initialize with variables, no prompts
        undatum pipeline templates init s3-etl --output etl.yml --var input_bucket=my-bucket --no-interactive
    """
    from ..cmds.pipeline_templates import TemplateManager

    if verbose:
        enable_verbose()

    variables = {}
    if var:
        for v in var:
            if "=" not in v:
                raise ValidationError(
                    f"Invalid variable format: {v}",
                    field="var",
                    suggestions=["Use key=value format, e.g. --var input_file=data.csv"],
                )
            key, value = v.split("=", 1)
            variables[key.strip()] = value.strip()

    manager = TemplateManager()
    if not manager.get_template(template_name):
        available = [tpl["name"] for tpl in manager.list_templates()]
        raise ValidationError(
            f"Template '{template_name}' not found",
            field="template_name",
            suggestions=available if available else None,
        )

    # Prompts need a terminal; in scripts and CI the template defaults and --var apply.
    success = manager.init_template(
        template_name, output, variables=variables, interactive=interactive and sys.stdin.isatty()
    )
    if not success:
        raise UndatumError(f"Failed to initialize template '{template_name}'")
