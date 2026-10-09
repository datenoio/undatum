"""LangChain tool bundle for undatum agent tools."""

from __future__ import annotations

from typing import Any

from . import schemas


def get_tools(root: str | None = None, allow_anywhere: bool = False) -> list[Any]:
    """Return LangChain ``StructuredTool`` instances for undatum operations.

    Covers the iterabledata foundation tools, undatum-specific tools (DuckDB SQL,
    frequency, ...) and one tool per registered operation. Tool paths are confined to
    ``root`` (default: the current directory) unless ``allow_anywhere`` is set.

    Requires ``langchain-core`` (``pip install langchain-core``).
    """
    from .sandbox import configure_sandbox

    configure_sandbox(root, allow_anywhere=allow_anywhere)
    try:
        from langchain_core.tools import StructuredTool
    except ImportError as err:
        raise ImportError(
            "langchain-core is required. Install with: pip install langchain-core"
        ) from err

    tools = []
    for definition in schemas.TOOL_DEFINITIONS:
        name = definition["name"]

        def _make_func(tool_name: str):
            def _run(**kwargs: Any) -> dict[str, Any]:
                return schemas.call_tool(tool_name, kwargs)

            return _run

        tools.append(
            StructuredTool.from_function(
                func=_make_func(name),
                name=name,
                description=definition["description"],
                # The JSON Schema of the tool, so agents see every parameter.
                args_schema=definition["parameters"],
            )
        )
    return tools
