"""CLI commands for the file-backed Data API."""

from typing import Annotated

import typer

api_app = typer.Typer(help="File-backed Data API commands.")


@api_app.command("discover")
def api_discover(
    input_files: Annotated[list[str], typer.Argument(help="Input file(s) to expose via API.")],
    output: Annotated[str | None, typer.Option(help="Output API config path.")] = None,
    format_in: Annotated[
        str | None, typer.Option(help="Override input format (e.g., 'csv').")
    ] = None,
    config_format: Annotated[str | None, typer.Option(help="Config format: yaml or json.")] = None,
    default_limit: Annotated[int, typer.Option(help="Default pagination limit.")] = 50,
    max_limit: Annotated[int, typer.Option(help="Max pagination limit.")] = 1000,
    allowed_ops: Annotated[
        str | None, typer.Option(help="Allowed ops CSV (eq,ne,lt,gt,le,ge,like).")
    ] = None,
):
    """Generate an API config from input files."""
    from ..cmds.api import DataApi

    options = {
        "output": output,
        "format_in": format_in,
        "config_format": config_format,
        "default_limit": default_limit,
        "max_limit": max_limit,
        "allowed_ops": allowed_ops,
    }
    DataApi().discover(input_files, options)


@api_app.command("serve")
def api_serve(
    config: Annotated[str, typer.Option(help="Path to API config file.")],
    host: Annotated[str, typer.Option(help="Host to bind (default: 127.0.0.1).")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to bind (default: 8000).")] = 8000,
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            help="Optional API key. Also read from UNDATUM_API_KEY. Clients send X-API-Key.",
        ),
    ] = None,
    cors_origins: Annotated[
        str | None,
        typer.Option(
            "--cors-origins",
            help="Comma-separated CORS origins for browser clients (e.g. https://app.example.com).",
        ),
    ] = None,
    query_timeout: Annotated[
        float | None,
        typer.Option(
            "--query-timeout",
            help="Seconds before a query is cancelled with HTTP 504 (default 30; 0 disables).",
        ),
    ] = None,
):
    """Serve API using a config file."""
    from ..cmds.api import DataApi, require_api_dependencies

    require_api_dependencies()
    options = {
        "host": host,
        "port": port,
        "api_key": api_key,
        "cors_origins": cors_origins,
        "query_timeout": query_timeout,
    }
    DataApi().serve(config, options)


@api_app.command("run")
def api_run(
    input_files: Annotated[list[str], typer.Argument(help="Input file(s) to expose via API.")],
    format_in: Annotated[
        str | None, typer.Option(help="Override input format (e.g., 'csv').")
    ] = None,
    default_limit: Annotated[int, typer.Option(help="Default pagination limit.")] = 50,
    max_limit: Annotated[int, typer.Option(help="Max pagination limit.")] = 1000,
    allowed_ops: Annotated[
        str | None, typer.Option(help="Allowed ops CSV (eq,ne,lt,gt,le,ge,like).")
    ] = None,
    host: Annotated[str, typer.Option(help="Host to bind (default: 127.0.0.1).")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to bind (default: 8000).")] = 8000,
    api_key: Annotated[
        str | None,
        typer.Option(
            "--api-key",
            help="Optional API key. Also read from UNDATUM_API_KEY. Clients send X-API-Key.",
        ),
    ] = None,
    cors_origins: Annotated[
        str | None,
        typer.Option(
            "--cors-origins",
            help="Comma-separated CORS origins for browser clients (e.g. https://app.example.com).",
        ),
    ] = None,
    query_timeout: Annotated[
        float | None,
        typer.Option(
            "--query-timeout",
            help="Seconds before a query is cancelled with HTTP 504 (default 30; 0 disables).",
        ),
    ] = None,
):
    """Discover resources from files and serve immediately."""
    from ..cmds.api import DataApi, require_api_dependencies

    require_api_dependencies()
    options = {
        "format_in": format_in,
        "default_limit": default_limit,
        "max_limit": max_limit,
        "allowed_ops": allowed_ops,
        "host": host,
        "port": port,
        "api_key": api_key,
        "cors_origins": cors_origins,
        "query_timeout": query_timeout,
    }
    DataApi().run(input_files, options)


@api_app.command("openapi")
def api_openapi(
    config: Annotated[str, typer.Option(help="Path to API config file.")],
    output: Annotated[
        str | None, typer.Option("--output", "-o", help="Write OpenAPI schema to this path.")
    ] = None,
    format: Annotated[
        str | None, typer.Option(help="Output format: json or yaml (default: json).")
    ] = None,
):
    """Export OpenAPI schema for an API config without starting the server."""
    from ..cmds.api import DataApi, require_api_dependencies

    require_api_dependencies()
    options = {"output": output, "format": format}
    DataApi().export_openapi(config, options)
