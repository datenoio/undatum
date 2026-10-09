"""Agent tools generated from the operation registry.

Every operation in :data:`undatum.ops.REGISTRY` becomes a tool named like the CLI command.
Its JSON Schema comes from the operation's configuration dataclass (types, defaults,
``choices`` metadata, and the ``Args:`` section of its docstring). Other inputs of
multi-input operations (``join``, ``exclude``, ``cat``) are passed as file paths
(``*_path`` / ``*_paths``) so the sandbox can check them.

Without ``output_path`` a tool is read-only and returns up to ``limit`` records inline.
With ``output_path`` it writes a file and requires ``confirm=true``.
"""

from __future__ import annotations

import dataclasses
import inspect
import itertools
import re
import typing
from collections.abc import Iterable
from typing import Any

from iterable.tools import tool_error, tool_success

# Reader options every generated tool accepts.
READER_OPTIONS: dict[str, dict[str, Any]] = {
    "format_in": {"type": "string", "description": "Input format when detection is wrong"},
    "table": {"type": "string", "description": "Table or sheet name for multi-table sources"},
    "flatten_nested": {
        "type": "boolean",
        "default": False,
        "description": "Unfold nested dict / array-of-dict fields onto dotted paths",
    },
}
COMMON_PROPERTIES: dict[str, dict[str, Any]] = {
    "input_path": {"type": "string", "description": "Input file"},
    "output_path": {
        "type": "string",
        "description": "Write the result here (requires confirm=true); omit to get records inline",
    },
    "confirm": {"type": "boolean", "default": False, "description": "Allow writing output_path"},
    "limit": {
        "type": "integer",
        "default": 100,
        "description": "Records returned inline when output_path is omitted",
    },
}
# Operations not exposed to agents, with the reason (shown by the parity report).
EXCLUDED: dict[str, str] = {}


def _field_docs(cls: type) -> dict[str, str]:
    """``Args:`` entries of a docstring, by name."""
    doc = inspect.getdoc(cls) or ""
    docs: dict[str, str] = {}
    current = None
    in_args = False
    for line in doc.splitlines():
        if line.strip() == "Args:":
            in_args = True
            continue
        if in_args and line and not line.startswith(" "):
            break
        if not in_args:
            continue
        match = re.match(r"^\s{4}(\w+)(?: \([^)]*\))?:\s*(.*)$", line)
        if match:
            current = match.group(1)
            docs[current] = match.group(2)
        elif current and line.strip():
            docs[current] += " " + line.strip()
    return docs


def _summary(cls: type) -> str:
    doc = inspect.getdoc(cls) or ""
    return doc.split("\n\n", 1)[0].replace("\n", " ")


def _is_source(annotation: Any) -> bool:
    origin = typing.get_origin(annotation)
    return annotation is Iterable or origin in (Iterable, typing.get_origin(Iterable[Any]))


def _schema_for(annotation: Any) -> tuple[dict[str, Any], str]:
    """JSON Schema for a type, and its kind (``value``, ``source``, ``sources``)."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _schema_for(non_none[0])
    if _is_source(annotation):
        return {"type": "string", "description": "Path of the other input"}, "source"
    if origin is tuple:
        item = args[0] if args else Any
        if _is_source(item):
            return {"type": "array", "items": {"type": "string"}}, "sources"
        return {"type": "array", "items": _schema_for(item)[0]}, "value"
    if origin in (frozenset, set, list):
        return {"type": "array", "items": _schema_for(args[0])[0] if args else {}}, "value"
    if origin is dict:
        return {"type": "object", "additionalProperties": _schema_for(args[1])[0]}, "value"
    simple = {str: "string", int: "integer", float: "number", bool: "boolean"}
    if annotation in simple:
        return {"type": simple[annotation]}, "value"
    return {}, "value"


def _config_fields(config_class: type) -> list[tuple[str, dict[str, Any], str, bool]]:
    """``(parameter name, schema, kind, required)`` for each config field."""
    hints = typing.get_type_hints(config_class)
    docs = _field_docs(config_class)
    out = []
    for f in dataclasses.fields(config_class):
        schema, kind = _schema_for(hints[f.name])
        schema = dict(schema)
        if f.name in docs:
            schema["description"] = docs[f.name]
        if "choices" in f.metadata:
            schema["enum"] = list(f.metadata["choices"])
        required = f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING
        if not required and f.default is not dataclasses.MISSING:
            default = f.default
            if isinstance(default, (str, int, float, bool)) and default is not None:
                schema["default"] = default
        name = (
            f"{f.name}_path"
            if kind == "source"
            else (f"{f.name}_paths" if kind == "sources" else f.name)
        )
        out.append((name, schema, kind, required))
    return out


def _config_class(op: Any) -> type:
    """The configuration dataclass of an operation (from its ``apply`` annotation)."""
    hints = typing.get_type_hints(type(op).apply)
    return typing.cast(type, hints["cfg"])


def tool_definitions() -> list[dict[str, Any]]:
    """Tool definitions (name, description, JSON Schema parameters) for every operation."""
    from ..ops import REGISTRY, get_operation

    get_operation("head")  # make sure the built-in operations are registered
    tools = []
    for name, op in sorted(REGISTRY.items()):
        if name in EXCLUDED:
            continue
        config_class = _config_class(op)
        properties = dict(COMMON_PROPERTIES)
        required = ["input_path"]
        for param, schema, _kind, is_required in _config_fields(config_class):
            properties[param] = schema
            if is_required:
                required.append(param)
        properties.update(READER_OPTIONS)
        description = (
            f"{_summary(config_class)} ({_summary(type(op)) or name}) "
            "Returns records inline, or writes output_path with confirm=true."
        )
        tools.append(
            {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": properties, "required": required},
            }
        )
    return tools


def call_generated(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run the generated tool ``name`` (arguments already checked by the sandbox)."""
    from ..io import RowSource
    from ..ops import get_operation, run
    from ..utils import normalize_for_json

    try:
        op = get_operation(name)
    except KeyError as exc:
        return tool_error(str(exc), code="unknown_tool")
    args = dict(arguments)
    input_path = args.pop("input_path", None)
    if not input_path:
        return tool_error("input_path is required", code="invalid_arguments")
    output_path = args.pop("output_path", None)
    confirm = bool(args.pop("confirm", False))
    limit = int(args.pop("limit", 100) or 100)
    reader = {key: args.pop(key) for key in list(args) if key in READER_OPTIONS}
    config_class = _config_class(op)
    kwargs: dict[str, Any] = {}
    try:
        hints = typing.get_type_hints(config_class)
        for param, _schema, kind, _required in _config_fields(config_class):
            if param not in args or args[param] is None:
                continue
            value = args.pop(param)
            field_name = param.removesuffix("_paths").removesuffix("_path")
            if kind == "source":
                value = RowSource(value, reader)
            elif kind == "sources":
                value = tuple(RowSource(path, reader) for path in value)
            else:
                value = _coerce(hints[field_name], value)
            kwargs[field_name] = value
        if args:
            return tool_error(
                f"Unknown arguments: {', '.join(sorted(args))}", code="invalid_arguments"
            )
        cfg = config_class(**kwargs)
    except (TypeError, ValueError) as exc:
        return tool_error(str(exc), code="invalid_arguments")

    source = RowSource(input_path, reader)
    try:
        if output_path:
            if not confirm:
                return tool_error(
                    f"{name} writes {output_path}; pass confirm=true to proceed.",
                    code="confirmation_required",
                )
            count = run(op, cfg, source, output_path)
            return tool_success({"output_path": output_path, "records": count})
        rows = list(itertools.islice(op.apply(source, cfg), limit + 1))
        records = [normalize_for_json(r) if isinstance(r, dict) else r for r in rows[:limit]]
        return tool_success(
            {"records": records, "count": len(records), "truncated": len(rows) > limit}
        )
    except Exception as exc:  # noqa: BLE001 - reported to the agent
        return tool_error(str(exc), code=f"{name}_failed")


def handler(name: str) -> Any:
    """A ``handler(**arguments)`` callable for the generated tool ``name``."""

    def run_tool(**arguments: Any) -> dict[str, Any]:
        return call_generated(name, arguments)

    run_tool.__name__ = name
    return run_tool


def _coerce(annotation: Any, value: Any) -> Any:
    """Turn JSON values into the config field's type (lists -> tuples / frozensets)."""
    origin = typing.get_origin(annotation)
    args = typing.get_args(annotation)
    if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)):
        non_none = [a for a in args if a is not type(None)]
        return _coerce(non_none[0], value) if len(non_none) == 1 else value
    if origin is tuple and isinstance(value, (list, tuple)):
        return tuple(value)
    if origin is frozenset and isinstance(value, (list, tuple, set)):
        return frozenset(value)
    if isinstance(value, str) and origin is tuple:
        return (value,)
    return value


def parity_report() -> list[dict[str, str]]:
    """For each CLI command: the agent tool that covers it, or why none does."""
    import click
    import typer.main

    from ..core import app
    from ..ops import REGISTRY
    from .schemas import TOOL_DEFINITIONS

    tool_names = {tool["name"] for tool in TOOL_DEFINITIONS}
    aliases = {
        "convert": "convert_file",
        "sql": "query_sql",
        "frequency": "frequency",
        "stats": "compute_stats",
        "analyze": "analyze_dataset",
        "schema": "infer_schema",
        "validate": "validate_data",
        "doc": "generate_documentation",
        "headers": "list_fields",
        "sniff": "sniff_file",
        "count": "count_records",
        "diff": "diff_files",
    }
    reasons = {
        "tui": "interactive terminal UI",
        "web": "local web server",
        "extract": "document extraction needs undatum[extract]; not exposed yet",
        "plot": "produces images",
        "split": "writes many files",
        "apply": "runs user Python code",
        "repack": "recompresses files in place",
        "ingest": "writes to databases",
        "flatten": "text output for humans",
        "table": "terminal output",
        "migrate-script": "rewrites the user's own scripts",
        "schema-drift": "compares many files; use infer_schema per file",
        "quality": "use compute_stats and validate_data, or the SDK's Dataset.quality()",
    }
    root = typer.main.get_command(app)
    ctx = root.context_class(root, info_name="undatum")
    rows = []
    for name in root.list_commands(ctx):  # type: ignore[attr-defined]
        command = root.get_command(ctx, name)  # type: ignore[attr-defined]
        if command is None or command.hidden or isinstance(command, click.Group):
            continue
        if hasattr(command, "list_commands"):
            continue
        tool = name if name in REGISTRY else aliases.get(name)
        if tool and tool in tool_names:
            rows.append({"command": name, "tool": tool, "note": ""})
        else:
            rows.append({"command": name, "tool": "", "note": reasons.get(name, "no tool yet")})
    return rows
