"""CLI commands that install the DuckDB extensions undatum uses, for offline machines."""

from typing import Annotated

import typer
from rich.table import Table

from .common import console
from .options import JsonOpt

extensions_app = typer.Typer(
    help=(
        "Install the DuckDB extensions undatum uses, so commands work without network access "
        "(they never download one while they run)."
    )
)

DirOpt = Annotated[
    str | None,
    typer.Option(
        "--dir",
        help="Extension directory (default: UNDATUM_DUCKDB_EXTENSION_DIR or ~/.duckdb/extensions).",
    ),
]


def _size(value: int | None) -> str:
    return f"{value / (1024 * 1024):.0f} MB" if value else "-"


def _print(rows: list[dict], directory: str, action: str | None = None) -> None:
    table = Table(show_header=True, header_style="bold")
    table.add_column("Extension")
    table.add_column("Installed")
    table.add_column("Size", justify="right")
    table.add_column("Used for")
    for row in rows:
        installed = "yes" if row["installed"] else "no"
        if action and row.get("downloaded"):
            installed = action
        table.add_row(row["name"], installed, _size(row["size"]), row["purpose"])
    console.print(table)
    console.print(f"Directory: {directory}")


@extensions_app.command(name="list")
def extensions_list(directory: DirOpt = None, as_json: JsonOpt = False):
    """List the DuckDB extensions undatum uses and whether they are installed.

    Examples:
        undatum extensions list
        undatum extensions list --dir /opt/duckdb-extensions --json
    """
    from ..common.duckdb_extensions import extension_directory, extension_status

    rows = extension_status(directory)
    target = extension_directory(directory)
    if as_json:
        from ..common.results import EXTENSIONS, emit

        emit(EXTENSIONS, {"directory": target, "extensions": rows})
        return
    _print(rows, target)


@extensions_app.command(name="install")
def extensions_install(
    names: Annotated[
        list[str] | None,
        typer.Argument(help="Extensions to install (default: all that undatum uses)."),
    ] = None,
    directory: DirOpt = None,
    force: Annotated[
        bool, typer.Option("--force", help="Download again when already installed.")
    ] = False,
    as_json: JsonOpt = False,
):
    """Download DuckDB extensions into the extension directory and check that they load.

    Run it on a machine with network access; copy the directory to offline machines and set
    UNDATUM_DUCKDB_EXTENSION_DIR there.

    Examples:
        undatum extensions install
        undatum extensions install encodings excel --dir /opt/duckdb-extensions
    """
    from ..common.duckdb_extensions import EXTENSIONS, extension_directory, install_extensions
    from ..common.errors import ValidationError

    chosen = list(dict.fromkeys(names or EXTENSIONS))
    unknown = [name for name in chosen if name not in EXTENSIONS]
    if unknown:
        raise ValidationError(
            f"Unknown extension: {', '.join(unknown)}",
            field="names",
            suggestions=list(EXTENSIONS),
        )
    rows = install_extensions(chosen, directory, force=force)
    target = extension_directory(directory)
    if as_json:
        from ..common.results import EXTENSIONS as LAYOUT
        from ..common.results import emit

        emit(LAYOUT, {"directory": target, "extensions": rows})
        return
    _print(rows, target, action="downloaded")
