"""The command-line interface as data: the manifest and agent tool definitions.

``undatum commands --json`` prints the manifest (``undatum.commands/1``) and ``--tools`` one
tool definition per command. Both are generated from the Click command tree when they run, so
they include plugin commands and always match ``--help``. ``scripts/generate_cli_reference.py``
walks the same tree with :func:`walk`.

Tool parameters are named after the long option (``--format-in`` is ``format_in``) or after the
argument; :func:`tool_argv` turns a tool call back into the command line.
"""

from __future__ import annotations

import re
from collections.abc import Iterator, Mapping, Sequence
from typing import Any

from ..common.errors import EXIT_CODES, UndatumError
from .capabilities import CAPABILITIES

ENGINES = ["auto", "duckdb", "python"]
TOOL_PREFIX = "undatum_"

# Click and Typer versions name the same types differently (TEXT/str, INTEGER/int).
JSON_TYPES = {"integer": "integer", "int": "integer", "float": "number"}


def root_context() -> Any:
    """Context of the ``undatum`` command group, built from the Typer application.

    Commands run without the group (see ``UndatumGroup.main``), so the manifest builds it.
    """
    import typer.main

    from ..core import app

    root = typer.main.get_command(app)
    return root.context_class(root, info_name="undatum")


def walk(command: Any, path: str, ctx: Any, groups: bool = False) -> Iterator[tuple[str, Any, Any]]:
    """Yield ``(path, command, ctx)`` for every visible leaf command below ``command``.

    Args:
        command: Command or group to start from.
        path: Its path without ``undatum`` (``""`` for the root).
        ctx: Its context.
        groups: Also yield the groups (before their commands).
    """
    if _is_group(command):
        if groups and path:
            yield path, command, ctx
        for name in command.list_commands(ctx):
            sub = command.get_command(ctx, name)
            if sub is None or sub.hidden:
                continue
            sub_ctx = sub.context_class(sub, info_name=name, parent=ctx)
            yield from walk(sub, f"{path} {name}".strip(), sub_ctx, groups)
    else:
        yield path, command, ctx


def _is_group(command: Any) -> bool:
    # typer vendors Click; its classes are not those of the click package.
    return hasattr(command, "list_commands")


def _text(help_text: str | None) -> str:
    text = re.sub(r"\s*\[default: [^\]]*\]", "", help_text or "")
    return " ".join(text.split())


def _help_and_examples(command: Any) -> tuple[str, list[str]]:
    """The help text of a command without its ``Examples:`` section, and the examples."""
    lines = [line for line in (command.help or "").splitlines() if line.strip() != "\b"]
    for index, line in enumerate(lines):
        if line.strip() in ("Example:", "Examples:"):
            examples = []
            for example in lines[index + 1 :]:
                if example.strip() and not example[:1].isspace():
                    break
                if example.strip():
                    examples.append(example.strip())
            return "\n".join(lines[:index]).strip(), examples
    return "\n".join(lines).strip(), []


def _type(param: Any) -> tuple[str, list[str] | None]:
    """JSON type and choices of a parameter."""
    choices = getattr(param.type, "choices", None)
    if choices:
        return "string", [str(getattr(choice, "value", choice)) for choice in choices]
    if getattr(param, "count", False):
        return "integer", None
    name = (param.type.name or "").lower()
    if getattr(param, "is_flag", False) or name in ("boolean", "bool"):
        return "boolean", None
    return JSON_TYPES.get(name, "string"), None


def _default(param: Any) -> Any:
    default = param.default
    if isinstance(default, (list, tuple)):
        default = [getattr(value, "value", value) for value in default] or None
    else:
        default = getattr(default, "value", default)
    if default is None or default == "" or not isinstance(default, (str, int, float, list)):
        return None  # callables, Click's unset sentinel
    return default


def _argument(param: Any) -> dict[str, Any]:
    kind, choices = _type(param)
    return {
        "name": param.name,
        "type": kind,
        "choices": choices,
        "default": _default(param),
        "required": param.required,
        "multiple": param.nargs == -1,
        "help": _text(getattr(param, "help", None)),
    }


def _option(param: Any, aliases: Mapping[str, str]) -> dict[str, Any]:
    # Long flags first, each group in declared order: the first long flag is the canonical one.
    flags = sorted(param.opts, key=lambda flag: not flag.startswith("--"))
    long = flags[0] if flags[0].startswith("--") else None
    kind, choices = _type(param)
    return {
        "name": long[2:].replace("-", "_") if long else param.name,
        "flags": flags,
        "negation": param.secondary_opts[0] if param.secondary_opts else None,
        "type": kind,
        "choices": choices,
        "default": _default(param),
        "required": param.required,
        "multiple": param.multiple,
        "flag": param.is_flag and not param.count,
        "count": param.count,
        "deprecated_flags": sorted(old for old, new in aliases.items() if new in param.opts),
        "help": _text(param.help),
    }


def _options(command: Any) -> list[dict[str, Any]]:
    aliases = getattr(command, "_undatum_aliases", {})
    return [
        _option(param, aliases)
        for param in command.params
        if param.param_type_name == "option"
        and not param.hidden
        and "--help" not in param.opts
        and not param.name.endswith("_completion")
    ]


def _usage(path: str, arguments: list[dict[str, Any]]) -> str:
    names = []
    for argument in arguments:
        name = argument["name"].upper() + ("..." if argument["multiple"] else "")
        names.append(name if argument["required"] else f"[{name}]")
    return " ".join(["undatum", path, "[OPTIONS]", *names])


def describe_command(path: str, command: Any) -> dict[str, Any]:
    """The manifest entry of one command (see :data:`undatum.common.results.COMMANDS`)."""
    from ..common.results import SCHEMAS

    help_text, examples = _help_and_examples(command)
    arguments = [_argument(p) for p in command.params if p.param_type_name == "argument"]
    options = _options(command)
    capability = CAPABILITIES.get(path)
    if any("--engine" in option["flags"] for option in options):
        engines: list[str] | None = ENGINES
    else:
        engines = ["python"] if capability is not None else None
    results = []
    for schema in SCHEMAS.values():  # "validate --rules": the options select the layout
        words = schema.command.split()
        name = " ".join(word for word in words if not word.startswith("-"))
        if name == path:
            when = " ".join(word for word in words if word.startswith("-"))
            results.append({"schema": schema.id, "when": when or None})
    return {
        "name": path,
        "summary": command.get_short_help_str(limit=300),
        "help": help_text,
        "examples": examples,
        "usage": _usage(path, arguments),
        "arguments": arguments,
        "options": options,
        "engines": engines,
        "capabilities": None
        if capability is None
        else {
            "reads": capability.reads,
            "writes": capability.writes,
            "memory": capability.memory,
        },
        "results": results,
        "deprecated": bool(command.deprecated),
    }


def _matches(path: str, words: Sequence[str]) -> bool:
    return path.split()[: len(words)] == list(words)


def manifest(
    words: Sequence[str] = (), search: str | None = None, ctx: Any = None
) -> dict[str, Any]:
    """The manifest of the CLI: global options, exit codes, groups and commands.

    Args:
        words: Keep only this command or the commands of this group (``["db"]``).
        search: Keep the commands whose name, summary or help contains every word.
        ctx: Context of the root group; built from the Typer application when omitted.

    Returns:
        The ``undatum.commands/1`` payload (without its ``schema`` key)

    Raises:
        UndatumError: ``words`` name no command or group.
    """
    from .. import __version__

    root = ctx or root_context()
    groups, commands = [], []
    for path, command, _ in walk(root.command, "", root, groups=True):
        if words and not _matches(path, words):
            continue
        if _is_group(command):
            groups.append({"name": path, "summary": command.get_short_help_str(limit=300)})
        else:
            commands.append(describe_command(path, command))
    if words and not commands:
        raise UndatumError(
            f"No command or group named '{' '.join(words)}'. Run 'undatum commands' for the list.",
            context={"command": " ".join(words)},
        )
    if search:
        terms = search.lower().split()
        commands = [
            entry
            for entry in commands
            if all(
                term in f"{entry['name']} {entry['summary']} {entry['help']}".lower()
                for term in terms
            )
        ]
        groups = [
            group
            for group in groups
            if any(_matches(entry["name"], group["name"].split()) for entry in commands)
        ]
    return {
        "undatum_version": __version__,
        "exit_codes": {str(code): meaning for code, meaning in EXIT_CODES.items()},
        "global_options": _options(root.command),
        "groups": groups,
        "commands": commands,
    }


def tool_name(path: str) -> str:
    """Tool name of a command: ``schema-drift`` -> ``undatum_schema_drift``."""
    return TOOL_PREFIX + re.sub(r"[^A-Za-z0-9]+", "_", path).strip("_")


def _schema(entry: Mapping[str, Any]) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": entry["type"]}
    if entry["choices"]:
        schema["enum"] = entry["choices"]
    if entry["multiple"]:
        schema = {"type": "array", "items": schema}
    if entry["default"] is not None:
        schema["default"] = entry["default"]
    if entry["help"]:
        schema["description"] = entry["help"]
    return schema


def tool_definition(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Tool definition (``name``, ``description``, ``parameters``) of a manifest entry."""
    properties = {}
    required = []
    for param in [*entry["arguments"], *entry["options"]]:
        properties[param["name"]] = _schema(param)
        if param["required"]:
            required.append(param["name"])
    description = entry["help"] or entry["summary"]
    if entry["results"]:
        layouts = "; ".join(
            f"{result['schema']} with {result['when']}" if result["when"] else result["schema"]
            for result in entry["results"]
        )
        description += f"\n\nJSON output layouts: {layouts}."
    return {
        "name": tool_name(entry["name"]),
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


def tool_definitions(commands: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Tool definitions of manifest entries (``manifest()["commands"]``)."""
    return [tool_definition(entry) for entry in commands]


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def tool_argv(
    name: str, arguments: Mapping[str, Any], commands: Sequence[Mapping[str, Any]] | None = None
) -> list[str]:
    """The command line (after ``undatum``) that runs a tool call.

    Args:
        name: Tool name (``undatum_count``) or command path (``"db query"``).
        arguments: Tool parameters; ``None`` values are left out.
        commands: Manifest entries; read from the CLI when omitted.

    Returns:
        Command-line words, e.g. ``["count", "--format-in", "csv", "data.csv"]``

    Raises:
        UndatumError: Unknown tool or parameter.

    Example:
        >>> tool_argv("undatum_head", {"input_file": "data.csv", "limit": 5})
        ['head', '--limit', '5', 'data.csv']
    """
    entries = commands if commands is not None else manifest()["commands"]
    entry = next((e for e in entries if name in (e["name"], tool_name(e["name"]))), None)
    if entry is None:
        raise UndatumError(f"Unknown undatum tool: {name}", context={"tool": name})
    known = {param["name"] for param in [*entry["arguments"], *entry["options"]]}
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise UndatumError(
            f"Unknown parameter(s) for {tool_name(entry['name'])}: {', '.join(unknown)}",
            context={"tool": tool_name(entry["name"]), "parameters": unknown},
        )
    options: list[str] = []
    for option in entry["options"]:
        value = arguments.get(option["name"])
        if value is None:
            continue
        flag = option["flags"][0]
        if option["count"]:
            options += [flag] * int(value)
        elif option["flag"]:
            if value:
                options.append(flag)
            elif option["negation"]:
                options.append(option["negation"])
        else:
            values = value if option["multiple"] and isinstance(value, (list, tuple)) else [value]
            for item in values:
                options += [flag, _value(item)]
    positionals: list[str] = []
    for argument in entry["arguments"]:
        value = arguments.get(argument["name"])
        if value is None:
            continue
        if argument["multiple"] and isinstance(value, (list, tuple)):
            positionals += [_value(item) for item in value]
        else:
            positionals.append(_value(value))
    if any(word.startswith("-") for word in positionals):
        positionals = ["--", *positionals]
    return [*entry["name"].split(), *options, *positionals]
