"""CLI naming conventions applied to every command in one place.

Commands are declared in many modules; this module enforces one vocabulary on the
built command tree instead of relying on each declaration:

- canonical long names (``--format-in``, ``--format-out``, ``--limit``, ...) replace
  historical spellings, which keep working as hidden aliases that print a
  deprecation warning (removal planned for 2.0);
- short flags (``-o``, ``-n``, ``-f``, ``-d``, ``-e``, ``-F``, ``-O``) are added where
  the command has the matching option and the letter is free;
- ``--engine`` accepts only ``auto``, ``duckdb`` and ``python`` (``iterable`` is an
  alias of ``python``);
- duplicate commands (``profile``, ``document``, ``ingest``, ``scheme``) are hidden and
  warn when used.
"""

from __future__ import annotations

import sys
from typing import Any

REMOVAL_VERSION = "2.0"

# Historical spelling -> canonical name, for every command that has the option.
RENAMES: dict[str, str] = {
    "--filetype": "--format-in",
    "--outtype": "--format-out",
    "--output-format": "--format-out",
    "--n": "--limit",
    "--objects-limit": "--limit",
}

# Commands where ``--format`` selects an output serialization, not a dialect.
FORMAT_MEANS_OUTPUT = {
    "ai doc",
    "api openapi",
    "diff",
    "doc",
    "document",
    "pipeline doc",
    "plot",
    "sniff",
    "sql",
}

# Inside the ``ai`` group the short names are canonical; the prefixed names used by
# other commands remain accepted.
AI_GROUP_RENAMES: dict[str, str] = {
    "--ai-provider": "--provider",
    "--ai-model": "--model",
    "--ai-base-url": "--base-url",
}

SHORT_FLAGS: dict[str, str] = {
    "--output": "-o",
    "--limit": "-n",
    "--fields": "-f",
    "--delimiter": "-d",
    "--engine": "-e",
    "--format-in": "-F",
    "--format-out": "-O",
}

# Hidden duplicate commands -> the canonical command to use instead.
DEPRECATED_COMMANDS: dict[str, str] = {
    "profile": "stats",
    "document": "doc",
    "ingest": "db load",
    "scheme": "schema --format cerberus",
}

ENGINES = ("auto", "duckdb", "python")
ENGINE_ALIASES = {"iterable": "python"}
ENGINE_HELP = "Processing engine: auto (default), duckdb, or python."

# Commands that write records through the shared writer; those without their own
# ``--format-out`` get one (handled centrally, see undatum.common.stdio).
RECORD_WRITERS = {
    "cat",
    "dedup",
    "enum",
    "exclude",
    "explode",
    "fill",
    "fixlengths",
    "head",
    "join",
    "rename",
    "replace",
    "reverse",
    "sample",
    "search",
    "slice",
    "sort",
    "tail",
    "transpose",
}
FORMAT_OUT_HELP = (
    "Output format (e.g. csv, jsonl, parquet). Defaults to the --output extension, or to the "
    "input's text format on stdout."
)


def _engine_callback(callback: Any) -> Any:
    """Wrap the callback of an ``--engine`` option so it gets a normalized, checked value.

    A callback rather than a parameter type: typer 0.29 builds the type of a parameter
    from its annotation and no longer has a ``type`` attribute to replace.
    """
    import typer

    def normalize(ctx: Any, param: Any, value: Any) -> Any:
        if isinstance(value, str):
            normalized = value.strip().lower()
            normalized = ENGINE_ALIASES.get(normalized, normalized)
            if normalized not in ENGINES:
                raise typer.BadParameter(
                    f"'{value}' is not one of: {', '.join(ENGINES)}.", ctx=ctx, param=param
                )
            value = normalized
        return value if callback is None else callback(ctx, param, value)

    return normalize


def _format_out_option(with_short: bool) -> Any:
    """Create a ``--format-out`` option, declared and built by typer like any other option.

    The value is consumed by the root group before parsing (``expose_value=False``), so
    command functions do not need a parameter for it.
    """
    import typer
    import typer.main

    names = ["--format-out", "-O"] if with_short else ["--format-out"]
    declaration = typer.Typer(add_completion=False)

    @declaration.command()
    def command(
        format_out: str | None = typer.Option(
            None, *names, help=FORMAT_OUT_HELP, metavar="FORMAT", show_default=False
        ),
    ) -> None:
        """Declare the option."""

    built = typer.main.get_command(declaration)
    option = next(param for param in built.params if param.name == "format_out")
    option.expose_value = False
    return option


def _warn(message: str) -> None:
    print(f"Warning: {message}", file=sys.stderr)


def _renames_for(path: str) -> dict[str, str]:
    renames = dict(RENAMES)
    if path in FORMAT_MEANS_OUTPUT:
        renames["--format"] = "--format-out"
    if path.startswith("ai "):
        renames.update(AI_GROUP_RENAMES)
    return renames


def apply_conventions(command: Any, path: str) -> None:
    """Apply naming conventions to ``command`` (idempotent).

    Records ``_undatum_aliases`` (deprecated spelling -> canonical spelling) on the
    command for :func:`rewrite_args`.
    """
    if getattr(command, "_undatum_conventions", False):
        return
    command._undatum_conventions = True
    aliases: dict[str, str] = {}
    params = [p for p in getattr(command, "params", []) if p.param_type_name == "option"]
    taken = {opt for p in params for opt in (*p.opts, *p.secondary_opts)}

    for old, new in _renames_for(path).items():
        owner = next((p for p in params if old in p.opts), None)
        if owner is None:
            continue
        if new in taken:
            # Another option already has the canonical name (an existing alias option):
            # hide this one and let the argument rewrite route old spellings to it.
            owner.hidden = True
        else:
            owner.opts = [new if opt == old else opt for opt in owner.opts]
            taken.discard(old)
            taken.add(new)
        aliases[old] = new

    for long_name, short in SHORT_FLAGS.items():
        owner = next((p for p in params if long_name in p.opts and not p.hidden), None)
        if owner is None or short in taken:
            continue
        owner.opts = [*owner.opts, short]
        taken.add(short)

    for param in params:
        if "--engine" in param.opts:
            param.callback = _engine_callback(param.callback)
            param.metavar = "[" + "|".join(ENGINES) + "]"
            param.help = ENGINE_HELP
            # Read by undatum.cli.manifest.param_type(): the declared type is a plain string.
            param._undatum_choices = ENGINES

    if path in RECORD_WRITERS and "--format-out" not in taken and params:
        command.params.append(_format_out_option("-O" not in taken))

    command._undatum_aliases = aliases


def rewrite_args(args: list[str], aliases: dict[str, str], path: str) -> list[str]:
    """Replace deprecated option spellings in ``args`` and warn once per spelling."""
    if not aliases:
        return args
    rewritten = []
    warned: set[str] = set()
    for token in args:
        if token == "--":
            rewritten.extend(args[len(rewritten) :])
            break
        name, sep, value = token.partition("=")
        if name in aliases:
            if name not in warned:
                _warn(
                    f"Option {name} is deprecated; use {aliases[name]} "
                    f"(removal in {REMOVAL_VERSION}) [undatum {path}]"
                )
                warned.add(name)
            token = aliases[name] + (sep + value if sep else "")
        rewritten.append(token)
    return rewritten


def warn_deprecated_command(name: str) -> None:
    """Print the deprecation notice for a hidden duplicate command."""
    _warn(
        f"Command '{name}' is deprecated; use 'undatum {DEPRECATED_COMMANDS[name]}' "
        f"(removal in {REMOVAL_VERSION})"
    )
