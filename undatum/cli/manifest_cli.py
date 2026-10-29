"""CLI command that describes the CLI: the command list, the manifest and tool definitions."""

from __future__ import annotations

from typing import Annotated

import typer

from .options import JsonOpt


def commands(
    words: Annotated[
        list[str] | None,
        typer.Argument(help="Command or group to describe (e.g. 'db' or 'formats list')."),
    ] = None,
    search: Annotated[
        str | None,
        typer.Option(
            "--search",
            "-s",
            help="Keep the commands whose name, summary or help contains every word.",
        ),
    ] = None,
    as_json: JsonOpt = False,
    tools: Annotated[
        bool,
        typer.Option(
            "--tools",
            help="Print one agent tool definition (JSON Schema parameters) per command.",
        ),
    ] = False,
):
    """List the commands, or describe them as data for scripts and agents.

    --json prints the manifest (undatum.commands/1): every command with its arguments, options,
    engines, capabilities, result schema and examples, plus the exit codes. --tools prints a
    tool definition per command, in the shape of 'undatum mcp tools --json'.

    Examples:
        undatum commands
        undatum commands --search duplicate
        undatum commands db --json
        undatum commands --tools > undatum-tools.json
    """
    from .manifest import manifest, tool_definitions

    if as_json and tools:
        raise typer.BadParameter("Use either --json or --tools.")
    payload = manifest(words or (), search)
    if as_json:
        from ..common.results import COMMANDS, emit

        emit(COMMANDS, payload)
        return
    if tools:
        from ..common.results import dumps

        typer.echo(dumps(tool_definitions(payload["commands"])))
        return

    from rich.table import Table

    from .common import console

    if not payload["commands"]:
        console.print(f"No command matches '{search}'.")
        return
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("Command", no_wrap=True)
    table.add_column("Summary")
    for entry in payload["commands"]:
        table.add_row(entry["name"], entry["summary"])
    console.print(table)
    console.print(
        "\nRun 'undatum COMMAND --help' for its options, "
        "or 'undatum commands --json' for all of them as data."
    )
