"""CLI commands for plugin management."""

import sys
from typing import Annotated

import typer
from rich.table import Table

from ..plugins.base import CommandPlugin, ConnectorPlugin, TransformPlugin
from ..plugins.manager import PluginManager
from .common import console, enable_verbose

plugins_app = typer.Typer(help="Plugin management commands.")

# Shared plugin manager instance; plugins are loaded by undatum.core at startup
plugin_manager = PluginManager()


@plugins_app.command(name="list")
def plugins_list(
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """List all installed plugins.

    Displays all plugins discovered via entry points with their metadata.

    Examples:
        # List all plugins
        undatum plugins list
    """
    if verbose:
        enable_verbose()

    registry = plugin_manager.get_registry()
    plugins = registry.list_plugins()

    if not plugins:
        console.print("[yellow]No plugins installed[/yellow]")
        return

    # Display plugins in a table
    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Description")
    table.add_column("Type")

    for plugin in plugins:
        plugin_type = []
        if isinstance(plugin, CommandPlugin):
            plugin_type.append("Command")
        if isinstance(plugin, ConnectorPlugin):
            plugin_type.append("Connector")
        if isinstance(plugin, TransformPlugin):
            plugin_type.append("Transform")

        table.add_row(
            plugin.name,
            plugin.version,
            plugin.description[:60] + "..." if len(plugin.description) > 60 else plugin.description,
            ", ".join(plugin_type) if plugin_type else "Base",
        )

    console.print(table)


@plugins_app.command()
def info(
    name: Annotated[str, typer.Argument(help="Plugin name.")],
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Show detailed information about a plugin.

    Displays plugin metadata, registered commands, connectors, and transforms.

    Examples:
        # Show plugin information
        undatum plugins info my-plugin
    """
    if verbose:
        enable_verbose()

    registry = plugin_manager.get_registry()
    plugin = registry.get_plugin(name)

    if not plugin:
        console.print(f"[red]Plugin '{name}' not found[/red]")
        sys.exit(1)

    # Display plugin information
    console.print(f"\n[bold cyan]Plugin: {plugin.name}[/bold cyan]")
    console.print(f"[bold]Version:[/bold] {plugin.version}")
    if plugin.description:
        console.print(f"[bold]Description:[/bold] {plugin.description}")

    # Show registered functionality
    if isinstance(plugin, CommandPlugin):
        console.print("\n[bold]Type:[/bold] Command Plugin")
        try:
            probe_app = typer.Typer()
            plugin.register_commands(probe_app)
            command_names = [
                cmd.name or (cmd.callback.__name__ if cmd.callback else "?")
                for cmd in probe_app.registered_commands
            ]
            if command_names:
                console.print(f"[bold]Commands:[/bold] {', '.join(sorted(command_names))}")
        except Exception as e:
            console.print(f"[yellow]Could not list commands: {e}[/yellow]")
    if isinstance(plugin, ConnectorPlugin):
        console.print("\n[bold]Type:[/bold] Connector Plugin")
        console.print(f"[bold]Connector:[/bold] {plugin.name}")
    if isinstance(plugin, TransformPlugin):
        console.print("\n[bold]Type:[/bold] Transform Plugin")
        console.print(f"[bold]Transform:[/bold] {plugin.name}")


@plugins_app.command()
def validate(
    name: Annotated[
        str | None,
        typer.Argument(help="Plugin name to validate. Omit to validate all loaded plugins."),
    ] = None,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Validate plugin structure, type, and basic callability.

    Checks that each plugin implements the expected interface for its type
    (command, connector, or transform).
    """
    if verbose:
        enable_verbose()

    registry = plugin_manager.get_registry()
    if name:
        plugins = [registry.get_plugin(name)]
        if plugins[0] is None:
            console.print(f"[red]Plugin '{name}' not found[/red]")
            sys.exit(1)
    else:
        plugins = registry.list_plugins()
        if not plugins:
            console.print("[yellow]No plugins installed[/yellow]")
            return

    errors = 0
    for plugin in plugins:
        problems = _validate_plugin(plugin)
        if problems:
            errors += 1
            console.print(f"[red]{plugin.name}[/red]: {'; '.join(problems)}")
        else:
            console.print(f"[green]{plugin.name}[/green]: ok ({plugin.version})")

    if errors:
        sys.exit(1)


def _validate_plugin(plugin) -> list[str]:
    """Return a list of validation problems for a plugin instance."""
    problems: list[str] = []
    if not getattr(plugin, "name", None):
        problems.append("missing name")
    if isinstance(plugin, CommandPlugin):
        if not callable(getattr(plugin, "register_commands", None)):
            problems.append("CommandPlugin must implement register_commands")
    if isinstance(plugin, ConnectorPlugin):
        if not callable(getattr(plugin, "can_handle", None)):
            problems.append("ConnectorPlugin must implement can_handle")
        if not callable(getattr(plugin, "open", None)):
            problems.append("ConnectorPlugin must implement open")
    if isinstance(plugin, TransformPlugin):
        if not callable(getattr(plugin, "transform", None)):
            problems.append("TransformPlugin must implement transform")
        else:
            try:
                result = plugin.transform({})
                if not isinstance(result, dict):
                    problems.append("transform() must return a dict")
            except Exception as exc:
                problems.append(f"transform() failed on empty record: {exc}")
    return problems
