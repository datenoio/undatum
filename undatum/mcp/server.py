"""Model Context Protocol server exposing undatum agent tools.

Surfaces undatum's tool layer (iterabledata foundation tools plus undatum
extras) over MCP stdio transport, mirroring iterabledata's ``iterable-mcp``
server but with undatum's richer command set. Each tool returns a JSON string
envelope (``{"ok": ..., ...}``).
"""

from __future__ import annotations

import json
from typing import Any

from ..tools import schemas


def _call(name: str, arguments: dict[str, Any]) -> str:
    return json.dumps(schemas.call_tool(name, arguments))


def _register_tools(mcp: Any) -> None:
    """Register undatum tools on a FastMCP instance."""

    # --- iterabledata foundation tools ---

    @mcp.tool()
    def detect_format(path: str) -> str:
        """Detect data format and compression for a file."""
        return _call("detect_format", {"path": path})

    @mcp.tool()
    def describe_capabilities(format_id: str) -> str:
        """Describe format metadata and capabilities."""
        return _call("describe_capabilities", {"format_id": format_id})

    @mcp.tool()
    def read_sample(path: str, n: int = 10, redact: bool = False) -> str:
        """Read a bounded sample of rows from a data file."""
        return _call("read_sample", {"path": path, "n": n, "redact": redact})

    @mcp.tool()
    def infer_schema(path: str) -> str:
        """Infer schema for a data file."""
        return _call("infer_schema", {"path": path})

    @mcp.tool()
    def analyze_dataset(path: str, autodoc: bool = False) -> str:
        """Analyze dataset structure; optional AI documentation."""
        return _call("analyze_dataset", {"path": path, "autodoc": autodoc})

    @mcp.tool()
    def compute_stats(path: str) -> str:
        """Compute column statistics for a data file."""
        return _call("compute_stats", {"path": path})

    @mcp.tool()
    def convert_file(
        input_path: str,
        output_path: str,
        confirm: bool = False,
        dry_run: bool = False,
    ) -> str:
        """Convert between formats. Writes require confirm=True."""
        return _call(
            "convert_file",
            {
                "input_path": input_path,
                "output_path": output_path,
                "confirm": confirm,
                "dry_run": dry_run,
            },
        )

    @mcp.tool()
    def generate_documentation(
        path: str, provider: str = "openai", doc_format: str = "json"
    ) -> str:
        """Generate AI-powered dataset documentation."""
        return _call(
            "generate_documentation",
            {"path": path, "provider": provider, "doc_format": doc_format},
        )

    @mcp.tool()
    def validate_data(path: str, rules: dict[str, list[str]], mode: str = "stats") -> str:
        """Validate rows against field rules; returns stats by default."""
        return _call("validate_data", {"path": path, "rules": rules, "mode": mode})

    @mcp.tool()
    def plan_conversion(source: str, target: str, use_llm: bool = False) -> str:
        """Produce a declarative conversion plan without writing files."""
        return _call("plan_conversion", {"source": source, "target": target, "use_llm": use_llm})

    @mcp.tool()
    def suggest_transform(path: str, goal: str) -> str:
        """Suggest a declarative transform spec (requires AI extras)."""
        return _call("suggest_transform", {"path": path, "goal": goal})

    @mcp.tool()
    def translate_filter(expression: str) -> str:
        """Translate a filter expression into a validated AST (DSL parsing; no LLM by default)."""
        return _call("translate_filter", {"expression": expression})

    # --- undatum-specific tools ---

    @mcp.tool()
    def query_sql(path: str, query: str, limit: int = 1000) -> str:
        """Run an ad-hoc DuckDB SQL query over a file (registered as the 'data' view)."""
        return _call("query_sql", {"path": path, "query": query, "limit": limit})

    @mcp.tool()
    def frequency(path: str, field: str, limit: int = 20, table: str | None = None) -> str:
        """Compute the value-frequency distribution for a top-level field."""
        return _call("frequency", {"path": path, "field": field, "limit": limit, "table": table})

    @mcp.tool()
    def deduplicate(
        input_path: str,
        output_path: str,
        keys: list[str] | None = None,
        keep: str = "first",
        confirm: bool = False,
        table: str | None = None,
    ) -> str:
        """Remove duplicate rows and write the result. Writes require confirm=True."""
        return _call(
            "deduplicate",
            {
                "input_path": input_path,
                "output_path": output_path,
                "keys": keys,
                "keep": keep,
                "confirm": confirm,
                "table": table,
            },
        )

    @mcp.tool()
    def mask_fields(
        input_path: str,
        output_path: str,
        fields: list[str],
        method: str = "redact",
        salt: str | None = None,
        confirm: bool = False,
        table: str | None = None,
    ) -> str:
        """Mask sensitive fields and write the result. Writes require confirm=True."""
        return _call(
            "mask_fields",
            {
                "input_path": input_path,
                "output_path": output_path,
                "fields": fields,
                "method": method,
                "salt": salt,
                "confirm": confirm,
                "table": table,
            },
        )

    @mcp.tool()
    def sample_data(
        input_path: str,
        output_path: str,
        n: int | None = None,
        percent: float | None = None,
        confirm: bool = False,
        table: str | None = None,
    ) -> str:
        """Write a random sample of rows. Writes require confirm=True."""
        return _call(
            "sample_data",
            {
                "input_path": input_path,
                "output_path": output_path,
                "n": n,
                "percent": percent,
                "confirm": confirm,
                "table": table,
            },
        )

    # --- informational tools: the documents of `undatum <command> --json` ---

    @mcp.tool()
    def count_records(path: str, format_in: str | None = None, table: str | None = None) -> str:
        """Count the records of a file (undatum.count/1 document)."""
        return _call("count_records", {"path": path, "format_in": format_in, "table": table})

    @mcp.tool()
    def list_fields(
        path: str,
        limit: int | None = None,
        format_in: str | None = None,
        table: str | None = None,
        flatten_nested: bool = False,
    ) -> str:
        """List field names in file order (undatum.headers/1 document)."""
        return _call(
            "list_fields",
            {
                "path": path,
                "limit": limit,
                "format_in": format_in,
                "table": table,
                "flatten_nested": flatten_nested,
            },
        )

    @mcp.tool()
    def sniff_file(path: str, format_in: str | None = None, table: str | None = None) -> str:
        """Detect format, compression, encoding, delimiter, fields, count (undatum.sniff/1)."""
        return _call("sniff_file", {"path": path, "format_in": format_in, "table": table})

    @mcp.tool()
    def diff_files(
        left_path: str,
        right_path: str,
        key: list[str] | None = None,
        ignore_order: bool = False,
        summary_only: bool = False,
        limit: int = 100,
    ) -> str:
        """Compare two files: added, removed and changed records (undatum.diff/1)."""
        return _call(
            "diff_files",
            {
                "left_path": left_path,
                "right_path": right_path,
                "key": key,
                "ignore_order": ignore_order,
                "summary_only": summary_only,
                "limit": limit,
            },
        )


def create_mcp_server(
    name: str = "undatum", root: str | None = None, allow_anywhere: bool = False
) -> Any:
    """Create a FastMCP server with undatum tools registered.

    Args:
        name: Server name advertised to MCP clients.
        root: Directory that tool paths must stay within (default: current directory).
        allow_anywhere: Disable the filesystem sandbox (trusted local use only).
    """
    from ..tools.sandbox import configure_sandbox

    configure_sandbox(root, allow_anywhere=allow_anywhere)
    try:
        # mcp 2.x renamed FastMCP to MCPServer; the tool API is the same.
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:
        try:
            from mcp.server.fastmcp import FastMCP as Server
        except ImportError as err:
            raise ImportError(
                'mcp package is required. Install with: pip install "undatum[mcp]"'
            ) from err

    mcp = Server(name)
    _register_tools(mcp)
    _register_generated_tools(mcp)
    from .resources import register as register_resources

    register_resources(mcp)
    return mcp


_JSON_TYPES: dict[str, Any] = {"string": str, "integer": int, "number": float, "boolean": bool}


def _python_type(schema: dict[str, Any]) -> Any:
    """Python annotation for a JSON Schema fragment (FastMCP derives the schema back)."""
    kind = schema.get("type")
    if kind == "array":
        return list[_python_type(schema.get("items") or {})]  # type: ignore[misc]
    if kind == "object":
        return dict[str, Any]
    return _JSON_TYPES.get(kind or "", Any)


def _generated_tool_function(tool: dict[str, Any]) -> Any:
    """A function with a real signature for one generated tool definition."""
    import inspect

    parameters = tool["parameters"]
    required = set(parameters.get("required", []))
    signature_params = []
    from typing import Annotated, Literal

    from pydantic import Field  # installed with mcp

    for param, schema in parameters["properties"].items():
        annotation = _python_type(schema)
        if schema.get("enum"):
            annotation = Literal[tuple(schema["enum"])]
        if schema.get("description"):
            annotation = Annotated[annotation, Field(description=schema["description"])]
        if param in required:
            signature_params.append(
                inspect.Parameter(param, inspect.Parameter.KEYWORD_ONLY, annotation=annotation)
            )
        else:
            signature_params.append(
                inspect.Parameter(
                    param,
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=annotation | None,
                    default=schema.get("default"),
                )
            )

    def tool_function(**arguments: Any) -> str:
        return _call(tool["name"], {k: v for k, v in arguments.items() if v is not None})

    tool_function.__name__ = tool["name"]
    tool_function.__doc__ = tool["description"]
    tool_function.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
        signature_params, return_annotation=str
    )
    tool_function.__annotations__ = {p.name: p.annotation for p in signature_params}
    tool_function.__annotations__["return"] = str
    return tool_function


def _register_generated_tools(mcp: Any) -> None:
    """Register one tool per operation of the registry (see undatum.tools.generated)."""
    for tool in schemas.GENERATED_TOOL_DEFINITIONS:
        mcp.add_tool(
            _generated_tool_function(tool), name=tool["name"], description=tool["description"]
        )


def main() -> None:
    """Entry point for the ``undatum-mcp`` console script (stdio transport)."""
    create_mcp_server().run()


if __name__ == "__main__":
    main()
