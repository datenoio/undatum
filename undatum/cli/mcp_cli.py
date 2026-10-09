"""CLI command to run undatum's Model Context Protocol (MCP) server.

Exposes undatum's agent tools (the iterabledata foundation tools plus undatum
extras such as DuckDB SQL, frequency, dedup, mask, and sample) to MCP-compatible
agents over stdio. Requires the optional ``mcp`` dependency::

    pip install undatum[mcp]
"""

import json
import logging
from typing import Annotated

import typer

from .common import console, enable_verbose

logger = logging.getLogger(__name__)

mcp_app = typer.Typer(help="Run or inspect undatum's MCP (Model Context Protocol) server.")


@mcp_app.command()
def serve(
    name: Annotated[str, typer.Option(help="Server name advertised to MCP clients.")] = "undatum",
    root: Annotated[
        str | None,
        typer.Option(
            "--root",
            help="Directory agent tools may read and write (default: current directory).",
        ),
    ] = None,
    allow_anywhere: Annotated[
        bool,
        typer.Option(
            "--allow-anywhere",
            help="Disable the filesystem sandbox. Only for trusted, local use.",
        ),
    ] = False,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Start the undatum MCP server over stdio.

    Wire this command into an MCP client (e.g. Claude Desktop, Cursor) as the
    server command. It speaks MCP over stdio and exposes undatum's agent tools.
    Tools can only touch files under ``--root``; SQL is read-only and cannot
    reach files outside it.

    Examples:
        undatum mcp serve
        undatum mcp serve --root ./data
    """
    if verbose:
        enable_verbose()

    try:
        from ..mcp.server import create_mcp_server
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    try:
        server = create_mcp_server(name=name, root=root, allow_anywhere=allow_anywhere)
    except ImportError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    if allow_anywhere:
        logger.warning("MCP filesystem sandbox disabled (--allow-anywhere)")
    logger.debug("Starting undatum MCP server '%s' (stdio)", name)
    server.run()


@mcp_app.command(name="tools")
def list_tools(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    parity: Annotated[
        bool,
        typer.Option("--parity", help="List CLI commands with the tool that covers each."),
    ] = False,
):
    """List the agent tools the MCP server exposes.

    Examples:
        undatum mcp tools
        undatum mcp tools --json
        undatum mcp tools --parity
    """
    from ..tools import schemas

    if parity:
        _print_parity(as_json)
        return
    definitions = schemas.TOOL_DEFINITIONS
    if as_json:
        console.print_json(json.dumps(definitions))
        return

    from rich.table import Table

    table = Table(show_header=True, header_style="bold", title="undatum MCP tools")
    table.add_column("Tool")
    table.add_column("Description")
    for definition in definitions:
        desc = definition["description"]
        if len(desc) > 70:
            desc = desc[:70] + "..."
        table.add_row(definition["name"], desc)
    console.print(table)
    console.print(f"\n[bold]{len(definitions)}[/bold] tools")


def _print_parity(as_json: bool) -> None:
    from rich.table import Table

    from ..tools.generated import parity_report

    rows = parity_report()
    if as_json:
        console.print_json(json.dumps(rows))
        return
    table = Table(show_header=True, header_style="bold", title="CLI commands and agent tools")
    table.add_column("Command")
    table.add_column("Tool")
    table.add_column("Note")
    from rich.markup import escape

    for row in rows:
        table.add_row(row["command"], row["tool"] or "-", escape(row["note"]))
    console.print(table)
    covered = sum(1 for row in rows if row["tool"])
    console.print(f"\n[bold]{covered}[/bold] of {len(rows)} commands have an agent tool")
