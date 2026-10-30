"""CLI commands that show and clear the cached command results (``~/.undatum/cache``)."""

from typing import Annotated

import typer

from .common import console
from .options import JsonOpt

cache_app = typer.Typer(
    help=(
        "Show or clear the results that stats, schema, sniff, analyze, headers and count keep "
        "for unchanged files."
    )
)


def _size(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


@cache_app.command(name="list")
def cache_list(as_json: JsonOpt = False):
    """List the cached files, their results and sizes.

    A file is stale when it is gone or changed; its results are no longer used.

    Examples:
        undatum cache list
        undatum cache list --json
    """
    from ..common.cache import cache_dir, entries

    rows = [{k: v for k, v in entry.items() if k != "_folder"} for entry in entries()]
    directory = str(cache_dir())
    if as_json:
        from ..common.results import CACHE, emit

        emit(CACHE, {"directory": directory, "entries": rows})
        return
    if not rows:
        console.print(f"No cached results in {directory}")
        return
    from rich.table import Table

    table = Table(show_header=True, header_style="bold")
    table.add_column("File")
    table.add_column("Results")
    table.add_column("Size", justify="right")
    table.add_column("State")
    for row in rows:
        commands = ", ".join(sorted({str(result["command"]) for result in row["results"]}))
        table.add_row(
            str(row["path"]), commands, _size(row["bytes"]), "stale" if row["stale"] else "current"
        )
    console.print(table)
    total = sum(row["bytes"] for row in rows)
    console.print(f"{len(rows)} files, {_size(total)} in {directory}")


@cache_app.command(name="clear")
def cache_clear(
    stale: Annotated[
        bool,
        typer.Option("--stale", help="Remove only the results of files that are gone or changed."),
    ] = False,
):
    """Remove cached results (all of them, or with --stale those of gone or changed files).

    Examples:
        undatum cache clear --stale
        undatum cache clear
    """
    from ..common.cache import cache_dir, clear

    removed, freed = clear(stale_only=stale)
    console.print(f"Removed the results of {removed} files ({_size(freed)}) from {cache_dir()}")
