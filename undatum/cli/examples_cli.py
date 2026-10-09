"""CLI commands for example recipes."""

import builtins
import logging
import sys
from typing import Annotated

import typer
from rich.table import Table

from .common import console, enable_verbose

logger = logging.getLogger(__name__)

examples_app = typer.Typer(help="Example recipes and workflows.")


@examples_app.command(name="list")
def examples_list(
    category: Annotated[str, typer.Option(help="Filter recipes by category.")] = None,
    tag: Annotated[str, typer.Option(help="Filter recipes by tag.")] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """List available example recipes.

    Displays all available recipes with their descriptions, categories, and tags.
    Use filters to narrow down the list.

    Examples:
        # List all recipes
        undatum examples list

        # List recipes by category
        undatum examples list --category conversion

        # List recipes by tag
        undatum examples list --tag database
    """
    from ..cmds.examples import RecipeManager

    if verbose:
        enable_verbose()

    manager = RecipeManager()
    recipes = manager.list_recipes(category=category, tag=tag)

    if not recipes:
        console.print("[yellow]No recipes found[/yellow]")
        return

    # Display recipes in a table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Category")
    table.add_column("Tags")

    for recipe in recipes:
        name = recipe.get("name", "")
        desc = (
            recipe.get("description", "")[:60] + "..."
            if len(recipe.get("description", "")) > 60
            else recipe.get("description", "")
        )
        cat = recipe.get("category", "")
        tags = (
            ", ".join(recipe.get("tags", []))[:40] + "..."
            if len(", ".join(recipe.get("tags", []))) > 40
            else ", ".join(recipe.get("tags", []))
        )

        table.add_row(name, desc, cat, tags)

    console.print(table)


@examples_app.command()
def show(
    name: Annotated[str, typer.Argument(help="Recipe name to display.")],
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Show detailed information about a recipe.

    Displays full recipe details including description, variables, commands, and examples.

    Examples:
        # Show recipe details
        undatum examples show csv-to-jsonl
    """
    from ..cmds.examples import RecipeManager

    if verbose:
        enable_verbose()

    manager = RecipeManager()
    manager.show_recipe(name)


@examples_app.command(name="run")
def examples_run(
    name: Annotated[str, typer.Argument(help="Recipe name to execute.")],
    var: Annotated[
        builtins.list[str],
        typer.Option(help="Variable values in key=value format (can be used multiple times)."),
    ] = None,
    dry_run: Annotated[bool, typer.Option(help="Show commands without executing them.")] = False,
    interactive: Annotated[
        bool, typer.Option(help="Prompt for variable values interactively.")
    ] = False,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Execute an example recipe.

    Runs a recipe with variable substitution. Variables can be provided via --var options
    or interactively with --interactive flag.

    Examples:
        # Run recipe with variables
        undatum examples run csv-to-jsonl --var input=data.csv --var output=data.jsonl

        # Preview commands without executing
        undatum examples run csv-to-jsonl --var input=data.csv --dry-run

        # Interactive mode
        undatum examples run csv-to-jsonl --interactive
    """
    from ..cmds.examples import RecipeManager

    if verbose:
        enable_verbose()

    # Parse variables
    variables = {}
    if var:
        for v in var:
            if "=" not in v:
                logger.error(f"Invalid variable format: {v}. Use key=value format.")
                sys.exit(1)
            key, value = v.split("=", 1)
            variables[key.strip()] = value.strip()

    manager = RecipeManager()
    manager.run_recipe(name, variables=variables, dry_run=dry_run, interactive=interactive)
