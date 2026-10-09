"""CLI commands for inspecting supported data formats.

Backed by iterabledata's machine-readable catalog (``iterable.catalog``) and
capability reporting (``iterable.helpers.capabilities``), so the list always
reflects the formats the underlying engine can actually handle.
"""

import json
import logging
from typing import Annotated

import typer
from rich.table import Table

from .common import console, enable_verbose
from .options import JsonOpt

logger = logging.getLogger(__name__)

formats_app = typer.Typer(help="Inspect supported data formats and their capabilities.")


def _bool_mark(value: bool | None) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "?"


def _cap_value(value) -> str:
    """Render a capability cell: booleans as yes/no, other values as text."""
    if isinstance(value, bool) or value is None:
        return _bool_mark(value)
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value) if value else ""
    return str(value)


# Capability columns shown (in order) when ``--capabilities`` is passed to list.
_CAPABILITY_COLUMNS = [
    ("bulk_read", "Bulk R"),
    ("bulk_write", "Bulk W"),
    ("streaming", "Stream"),
    ("totals", "Totals"),
    ("tables", "Tables"),
    ("nested", "Nested"),
    ("native_bulk_read", "NatR"),
    ("native_bulk_write", "NatW"),
]


@formats_app.command(name="list")
def formats_list(
    writable: Annotated[bool, typer.Option(help="Show only formats that support writing.")] = False,
    readable_only: Annotated[
        bool, typer.Option("--read-only", help="Show only read-only formats.")
    ] = False,
    capabilities: Annotated[
        bool,
        typer.Option(
            "--capabilities", "-c", help="Show the full runtime capability matrix per format."
        ),
    ] = False,
    as_json: JsonOpt = False,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """List all supported data formats and whether they are readable/writable.

    Capabilities come from iterabledata's runtime capability reporting
    (``iterable.helpers.capabilities``), so they reflect what the underlying
    engine (and installed optional dependencies) can actually do.

    Examples:
        # List every supported format
        undatum formats list

        # List only writable formats
        undatum formats list --writable

        # Show the full capability matrix (bulk, streaming, totals, tables, nested,
        # maturity, native bulk)
        undatum formats list --capabilities

        # Machine-readable output (includes the capabilities dict)
        undatum formats list --json
    """
    if verbose:
        enable_verbose()

    from iterable.catalog import describe_format, list_formats

    rows = []
    for fmt_id in list_formats():
        try:
            desc = describe_format(fmt_id)
        except Exception as e:  # noqa: BLE001
            logger.debug("Skipping format %s: %s", fmt_id, e)
            continue
        is_writable = bool(desc.get("writable"))
        if writable and not is_writable:
            continue
        if readable_only and is_writable:
            continue
        rows.append(
            {
                "id": desc.get("id", fmt_id),
                "writable": is_writable,
                "text": bool(desc.get("text")),
                "extra": desc.get("extra"),
                "maturity": desc.get("maturity")
                or (desc.get("capabilities") or {}).get("maturity"),
                "description": desc.get("description") or "",
                "capabilities": desc.get("capabilities") or {},
            }
        )

    if as_json:
        from ..common.results import FORMATS, emit

        emit(FORMATS, {"formats": rows})
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Format")
    table.add_column("Read")
    table.add_column("Write")
    table.add_column("Text")
    table.add_column("Maturity")
    if capabilities:
        for _key, label in _CAPABILITY_COLUMNS:
            table.add_column(label)
    else:
        table.add_column("Extra")
        table.add_column("Description")
    for row in rows:
        maturity = row.get("maturity") or (row.get("capabilities") or {}).get("maturity") or ""
        cells = [
            row["id"],
            "yes",
            _bool_mark(row["writable"]),
            _bool_mark(row["text"]),
            str(maturity),
        ]
        if capabilities:
            caps = row["capabilities"]
            cells.extend(_bool_mark(caps.get(key)) for key, _label in _CAPABILITY_COLUMNS)
        else:
            desc = row["description"]
            if len(desc) > 50:
                desc = desc[:50] + "..."
            cells.extend([row["extra"] or "", desc])
        table.add_row(*cells)
    console.print(table)
    console.print(f"\n[bold]{len(rows)}[/bold] formats")


@formats_app.command()
def describe(
    format_id: Annotated[str, typer.Argument(help="Format id or alias (e.g. 'csv', 'parquet').")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Show detailed metadata and capabilities for a single format.

    Examples:
        undatum formats describe parquet
        undatum formats describe geojson --json
    """
    if verbose:
        enable_verbose()

    from iterable.catalog import describe_format

    try:
        desc = describe_format(format_id)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    if as_json:
        console.print_json(json.dumps(desc, default=str))
        return

    console.print(f"[bold]{desc.get('id')}[/bold]")
    if desc.get("description"):
        console.print(desc["description"])
    aliases = desc.get("aliases") or []
    if aliases:
        console.print(f"[dim]Aliases:[/dim] {', '.join(aliases)}")
    console.print(f"[dim]Writable:[/dim] {_bool_mark(desc.get('writable'))}")
    console.print(f"[dim]Text format:[/dim] {_bool_mark(desc.get('text'))}")
    console.print(f"[dim]Flat/tabular:[/dim] {_bool_mark(desc.get('flat'))}")
    if desc.get("maturity"):
        console.print(f"[dim]Maturity:[/dim] {desc['maturity']}")
    if desc.get("extra"):
        console.print(f"[dim]Optional extra:[/dim] {desc['extra']}")
    if desc.get("doc_url"):
        console.print(f"[dim]Docs:[/dim] {desc['doc_url']}")
    if desc.get("read_memory"):
        console.print(f"[dim]Read memory:[/dim] {desc['read_memory']}")
    if desc.get("write_memory"):
        console.print(f"[dim]Write memory:[/dim] {desc['write_memory']}")
    if desc.get("native_bulk_read") is not None or desc.get("native_bulk_write") is not None:
        console.print(f"[dim]Native bulk read:[/dim] {_bool_mark(desc.get('native_bulk_read'))}")
        console.print(f"[dim]Native bulk write:[/dim] {_bool_mark(desc.get('native_bulk_write'))}")
    selection = desc.get("selection") or []
    if selection:
        console.print(f"[dim]Selection:[/dim] {', '.join(str(item) for item in selection)}")
    codecs = desc.get("codec_support") or []
    if codecs:
        console.print(f"[dim]Codecs:[/dim] {', '.join(str(item) for item in codecs)}")
    constraints = desc.get("source_constraints") or []
    if constraints:
        console.print(
            f"[dim]Source constraints:[/dim] {', '.join(str(item) for item in constraints)}"
        )
    example_args = desc.get("example_args") or {}
    if example_args:
        rendered = ", ".join(f"{key}={value}" for key, value in example_args.items())
        console.print(f"[dim]Example args:[/dim] {rendered}")

    limitations = desc.get("limitations") or []
    if limitations:
        console.print("[dim]Limitations:[/dim]")
        for item in limitations:
            console.print(f"  - {item}")

    caps = desc.get("capabilities") or {}
    if caps:
        table = Table(show_header=True, header_style="bold", title="Capabilities")
        table.add_column("Capability")
        table.add_column("Value")
        for key in sorted(caps):
            table.add_row(key, _cap_value(caps[key]))
        console.print(table)


@formats_app.command()
def export(
    output: Annotated[
        str, typer.Option(help="Output file path. Prints to stdout if not given.")
    ] = None,
    no_capabilities: Annotated[
        bool, typer.Option("--no-capabilities", help="Exclude runtime capabilities.")
    ] = False,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """Export the full format catalog as JSON.

    Examples:
        undatum formats export
        undatum formats export --output formats.json
    """
    if verbose:
        enable_verbose()

    from iterable.catalog import export_catalog

    payload = export_catalog(format="json", include_capabilities=not no_capabilities)
    if output:
        with open(output, "w", encoding="utf-8") as f:
            f.write(payload)
        console.print(f"[green]Catalog written to {output}[/green]")
    else:
        console.print_json(payload)


@formats_app.command()
def tables(
    source: Annotated[
        str, typer.Argument(help="File, directory, or URI to list tables/sheets from.")
    ],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    verbose: Annotated[bool, typer.Option(help="Enable verbose logging output.")] = False,
):
    """List named tables or sheets in a multi-table source.

    Works for Excel workbooks, SQLite/DuckDB files, and lakehouse directories.
    Use the printed name with ``undatum convert --table`` / ``--sheet``.

    Examples:
        undatum formats tables workbook.xlsx
        undatum formats tables data.sqlite --json
    """
    if verbose:
        enable_verbose()

    from ..common.command_utils import list_source_tables
    from ..common.path_utils import is_uri

    if not is_uri(source):
        from pathlib import Path

        if not Path(source).exists():
            console.print(f"[red]File not found: {source}[/red]")
            raise typer.Exit(code=1)

    names = list_source_tables(source)
    if names is None:
        console.print("[red]This source does not expose named tables or sheets.[/red]")
        raise typer.Exit(code=1)

    if as_json:
        console.print_json(json.dumps({"source": source, "tables": names}))
        return

    table = Table(show_header=True, header_style="bold", title=str(source))
    table.add_column("#")
    table.add_column("Table")
    for index, name in enumerate(names):
        table.add_row(str(index), name)
    console.print(table)
    console.print(f"\n[bold]{len(names)}[/bold] tables")
