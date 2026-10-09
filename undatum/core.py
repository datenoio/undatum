#!/usr/bin/env python
"""Main CLI assembly for the undatum package.

Composes the Typer application from per-domain CLI modules in
``undatum.cli`` and loads plugins. Individual command implementations
live in ``undatum.cli.commands`` and the other ``undatum.cli``
modules.
"""

import contextvars
import logging
import sys
from collections.abc import Sequence
from typing import Annotated, Any

import typer
from typer.core import TyperGroup

from . import __version__
from .cli.ai_cli import ai_app
from .cli.api_cli import api_app
from .cli.commands import data_app
from .cli.common import (
    configure_logging,
    enable_verbose,  # noqa: F401 - re-exported for backward compatibility
)
from .cli.config_cli import config_app
from .cli.db_cli import db_app
from .cli.examples_cli import examples_app
from .cli.formats_cli import formats_app
from .cli.mcp_cli import mcp_app
from .cli.package_cli import package_app
from .cli.pipeline_cli import pipeline_app, templates_app  # noqa: F401
from .cli.plugins_cli import plugin_manager, plugins_app
from .cli.tui_cli import tui as tui_command
from .cli.web_cli import web as web_command

logger = logging.getLogger(__name__)

# Entry point group for lazily loaded plugin commands: ``name = "pkg.module:obj"`` where
# ``obj`` is a ``typer.Typer`` app, a Click/Typer command, or a plain function. The module
# is imported only when the command runs or help is rendered.
PLUGIN_COMMANDS_GROUP = "undatum.commands"


def _plugin_command_entry_points() -> dict:
    from importlib.metadata import entry_points

    try:
        return {ep.name: ep for ep in entry_points(group=PLUGIN_COMMANDS_GROUP)}
    except Exception as exc:  # pragma: no cover - broken environment metadata
        logger.warning("Could not read %s entry points: %s", PLUGIN_COMMANDS_GROUP, exc)
        return {}


class UndatumGroup(TyperGroup):
    """Root command group.

    - adds plugin commands from the ``undatum.commands`` entry points without importing
      them up front;
    - applies the CLI naming conventions (:mod:`undatum.cli.conventions`) to every
      command, rewrites deprecated option spellings and hides duplicate commands.
    """

    def list_commands(self, ctx):
        names = super().list_commands(ctx)
        extra = [name for name in _plugin_command_entry_points() if name not in names]
        return names + sorted(extra)

    def get_command(self, ctx, cmd_name):
        command = super().get_command(ctx, cmd_name)
        if command is None:
            command = self._plugin_command(cmd_name)
        if command is not None:
            _apply_conventions_tree(command, cmd_name)
        return command

    def _plugin_command(self, cmd_name):
        cache = self.__dict__.setdefault("_plugin_cache", {})
        if cmd_name not in cache:
            cache[cmd_name] = self._load_plugin_command(cmd_name)
        return cache[cmd_name]

    def _load_plugin_command(self, cmd_name):
        entry_point = _plugin_command_entry_points().get(cmd_name)
        if entry_point is None:
            return None
        try:
            obj = entry_point.load()
        except Exception as exc:
            # A broken plugin must not break other commands.
            logger.warning("Failed to load plugin command '%s': %s", cmd_name, exc)
            return None
        if isinstance(obj, typer.Typer):
            return typer.main.get_command(obj)
        if hasattr(obj, "invoke") and hasattr(obj, "params"):
            return obj
        wrapper = typer.Typer()
        wrapper.command(name=cmd_name)(obj)
        return typer.main.get_command(wrapper)

    def main(
        self,
        args: Sequence[str] | None = None,
        prog_name: str | None = None,
        complete_var: str | None = None,
        standalone_mode: bool = True,
        windows_expand_args: bool = True,
        **extra: Any,
    ) -> Any:
        # Run each invocation in its own context so the stdout format chosen for one
        # command never leaks into the next (CliRunner, SDK use in the same process).
        run = contextvars.copy_context().run
        from .common.results import json_requested

        argv = sys.argv[1:] if args is None else list(args)
        if not standalone_mode or not json_requested(argv):
            return run(
                super().main,
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=standalone_mode,
                windows_expand_args=windows_expand_args,
                **extra,
            )
        # JSON mode: every failure becomes one JSON error object on stderr.
        try:
            result = run(
                super().main,
                args=args,
                prog_name=prog_name,
                complete_var=complete_var,
                standalone_mode=False,
                windows_expand_args=windows_expand_args,
                **extra,
            )
        except SystemExit:
            raise
        except BaseException as exc:  # noqa: BLE001 - reported as JSON
            _exit_with_json_error(exc)
        # Without standalone mode Click returns the code of ctx.exit() / typer.Exit.
        sys.exit(result if isinstance(result, int) else 0)

    def invoke(self, ctx):
        from .common.stdio import OutputClosed

        try:
            result = super().invoke(ctx)
            # Flush here so a closed pipe is reported now, not at interpreter exit.
            sys.stdout.flush()
            return result
        except BrokenPipeError as exc:
            raise OutputClosed() from exc

    def parse_args(self, ctx, args):
        return super().parse_args(ctx, self._rewrite_deprecated(ctx, list(args)))

    def _rewrite_deprecated(self, ctx, args):
        from .cli.conventions import DEPRECATED_COMMANDS, rewrite_args, warn_deprecated_command

        # Locate the command path (skipping root options such as -v / --quiet).
        index = next((i for i, token in enumerate(args) if not token.startswith("-")), None)
        if index is None:
            return args
        args = _command_spellings(args, index)
        name = args[index]
        command = self.get_command(ctx, name)
        if command is None:
            return args
        if name in DEPRECATED_COMMANDS:
            warn_deprecated_command(name)
        path = [name]
        position = index + 1
        while hasattr(command, "commands") and position < len(args):
            if args[position].startswith("-"):
                break
            child = command.commands.get(args[position])
            if child is None:
                break
            command = child
            path.append(args[position])
            position += 1
        aliases = getattr(command, "_undatum_aliases", {})
        rest = rewrite_args(args[position:], aliases, " ".join(path))
        return args[:position] + _prepare_stdio(command, rest)


# Two-word spellings of commands: ``undatum schema drift`` and ``undatum schema diff``
# (``schema`` itself takes a file, so these are rewritten before parsing).
_SPELLINGS = {("schema", "drift"): ["schema-drift"], ("schema", "diff"): ["diff", "--schema"]}


def _command_spellings(args: list[str], index: int) -> list[str]:
    """Rewrite ``schema drift ...`` -> ``schema-drift ...`` unless a file has that name."""
    import os

    if index + 1 < len(args):
        replacement = _SPELLINGS.get((args[index], args[index + 1]))
        if replacement and not os.path.exists(args[index + 1]):
            return args[:index] + replacement + args[index + 2 :]
    return args


def _exit_with_json_error(exc: BaseException) -> None:
    """Print ``exc`` as a JSON error object on stderr and exit with its code."""
    from .common.errors import exit_code_for
    from .common.results import dumps, error_document
    from .common.stdio import OutputClosed

    exit_code = getattr(exc, "exit_code", None)
    if type(exc).__name__ == "Exit" and isinstance(exit_code, int):
        sys.exit(exit_code)  # typer.Exit / ctx.exit(): not an error
    if isinstance(exc, (OutputClosed, BrokenPipeError)):
        raise exc
    if type(exc).__name__ == "Abort":
        exc = KeyboardInterrupt()
    code = exit_code_for(exc)
    sys.stderr.write(dumps(error_document(exc, code)) + "\n")
    sys.exit(code)


def _prepare_stdio(command, args):
    """Spool ``-`` (stdin) to a temporary file and pick the stdout format.

    The stdout format is ``--format-out`` when given, otherwise the text format of the
    first input file (CSV in, CSV out), otherwise JSON Lines.
    """
    from .common.stdio import (
        STDIN_PATH,
        format_out_override,
        spool_stdin,
        stdout_format,
        text_format_of,
    )

    value_options = set()
    for param in getattr(command, "params", []):
        if param.param_type_name == "option" and not (param.is_flag or param.count):
            value_options.update(param.opts)
            value_options.update(param.secondary_opts)

    def option_value(names):
        for i, token in enumerate(args):
            name, sep, value = token.partition("=")
            if name in names:
                if sep:
                    return value
                if i + 1 < len(args):
                    return args[i + 1]
        return None

    format_in = option_value({"--format-in", "-F"})
    format_out = option_value({"--format-out", "-O"})
    result = []
    positionals = []
    expecting_value = False
    for token in args:
        if expecting_value:
            expecting_value = False
            result.append(token)
            continue
        if token.startswith("-") and token != STDIN_PATH:
            name = token.partition("=")[0]
            expecting_value = name in value_options and "=" not in token
            result.append(token)
            continue
        if token == STDIN_PATH and not any(p == STDIN_PATH for p in positionals):
            positionals.append(token)
            token = spool_stdin(format_in)
        else:
            positionals.append(token)
        result.append(token)
    detected = next(
        (fmt for fmt in (text_format_of(t) for t in result if not t.startswith("-")) if fmt),
        None,
    )
    if format_in and text_format_of(f"x.{format_in.lower()}"):
        detected = format_in.lower()  # --format-in describes the input better than its name
    format_out_override.set(format_out.lower() if format_out else None)
    chosen = format_out or detected
    stdout_format.set(chosen.lower() if chosen else None)
    return result


def _apply_conventions_tree(command, path: str) -> None:
    from .cli.conventions import DEPRECATED_COMMANDS, apply_conventions

    if path in DEPRECATED_COMMANDS:
        command.hidden = True
    if hasattr(command, "commands"):
        for name, child in command.commands.items():
            _apply_conventions_tree(child, f"{path} {name}")
    else:
        apply_conventions(command, path)


app = typer.Typer(cls=UndatumGroup)


def _version_callback(value: bool):
    if value:
        typer.echo(f"undatum {__version__}")
        raise typer.Exit()


@app.callback()
def _main_callback(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = None,
    verbose: Annotated[
        int,
        typer.Option(
            "-v",
            "--verbose",
            count=True,
            help="More output on stderr: -v for progress messages, -vv for debug.",
        ),
    ] = 0,
    quiet: Annotated[
        bool, typer.Option("-q", "--quiet", help="Only print errors on stderr.")
    ] = False,
):
    """undatum: a command-line tool for data processing and analysis."""
    if quiet:
        configure_logging(-1)
    elif verbose:
        configure_logging(verbose)


# Merge top-level data commands into the main app
app.registered_commands.extend(data_app.registered_commands)
app.command("tui")(tui_command)
app.command("web")(web_command)

app.add_typer(ai_app, name="ai")
app.add_typer(package_app, name="package")
app.add_typer(api_app, name="api")
app.add_typer(config_app, name="config")
app.add_typer(pipeline_app, name="pipeline")
app.add_typer(db_app, name="db")
app.add_typer(examples_app, name="examples")
app.add_typer(formats_app, name="formats")
app.add_typer(mcp_app, name="mcp")
app.add_typer(plugins_app, name="plugins")

# Load and register plugins after app is fully initialized
try:
    plugin_manager.load_all_plugins(app)
    registry = plugin_manager.get_registry()
    for command_plugin in registry.get_command_plugins():
        try:
            command_plugin.register_commands(app)
        except Exception as e:
            logger.warning(f"Failed to register commands from plugin '{command_plugin.name}': {e}")
except Exception as e:
    logger.warning(f"Failed to load/register plugins: {e}")

# Sort commands alphabetically for help output
app.registered_commands.sort(
    key=lambda cmd: (cmd.name or (cmd.callback.__name__ if cmd.callback else "")).lower()
)


if __name__ == "__main__":
    app()
