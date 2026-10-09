"""Inspect resolved undatum configuration."""

from typing import Annotated, Any

import typer
import yaml

from ..common.app_config import describe_cli_config
from .options import JsonOpt

config_app = typer.Typer(help="Show resolved CLI defaults from config files and environment.")


def _dump(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


FormatOutOpt = Annotated[
    str,
    typer.Option("--format-out", "-O", help="Output format: 'yaml' (default) or 'json'."),
]


@config_app.callback(invoke_without_command=True)
def config_root(ctx: typer.Context) -> None:
    """Show resolved CLI defaults when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        _print_config()


@config_app.command("show")
def config_show(format_out: FormatOutOpt = "yaml", json_output: JsonOpt = False) -> None:
    """Print resolved CLI defaults and which config files were loaded."""
    _print_config("json" if json_output else format_out)


def _print_config(format_out: str = "yaml") -> None:
    config = describe_cli_config()
    if format_out.lower() == "json":
        from ..common.results import CONFIG, emit

        emit(CONFIG, config)
        return
    typer.echo(_dump(config).rstrip())
