"""Data API command module."""

from __future__ import annotations

import datetime
import decimal
import json
import logging
import os
import re
import sys
import tempfile
import uuid
from typing import Any, Optional

import yaml
from iterable.helpers.detect import detect_file_type
from pydantic import BaseModel, Field, create_model

from ..common.errors import FileNotFoundError, PermissionError, find_similar_files
from ..common.path_utils import (
    cloud_object_suffix,
    is_cloud_uri,
    is_s3_uri,
    is_uri,
    looks_like_missing_cloud_dep,
    missing_cloud_extra_error,
    validate_file_path,
)
from ..common.schema_utils import duckdb_decompose
from ..constants import DUCKABLE_FILE_TYPES
from ..utils import get_option

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_OPS = ["eq", "ne", "lt", "gt", "le", "ge", "like"]
DEFAULT_ORDER_DIRS = {"asc", "desc"}
DEFAULT_PAGINATION = {"default_limit": 50, "max_limit": 1000}
DEFAULT_QUERY_TIMEOUT = 30.0
RESERVED_QUERY_PARAMS = {
    "limit",
    "offset",
    "order_by",
    "order_dir",
    "sort",
    "include_total",
    "api_key",
}
OPERATOR_MAP = {
    "eq": "=",
    "ne": "!=",
    "lt": "<",
    "gt": ">",
    "le": "<=",
    "ge": ">=",
    "like": "LIKE",
}


class PaginationMeta(BaseModel):
    """Pagination metadata for list responses."""

    limit: int
    offset: int
    count: int
    total: int | None = None


def require_api_dependencies() -> None:
    """Raise DependencyError when the optional Data API extra is not installed."""
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as exc:
        from ..common.errors import DependencyError

        raise DependencyError(
            "fastapi",
            feature="Data API",
            install_command='pip install "undatum[api]"',
        ) from exc


def _normalize_resource_name(path: str, idx: int) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    name = re.sub(r"[^A-Za-z0-9_]+", "_", stem).strip("_").lower()
    if not name:
        return f"resource_{idx}"
    return name


def _unique_resource_name(base: str, used: set[str]) -> str:
    if base not in used:
        used.add(base)
        return base
    counter = 2
    while f"{base}_{counter}" in used:
        counter += 1
    name = f"{base}_{counter}"
    used.add(name)
    return name


def _detect_format(path: str, override: str | None) -> str | None:
    if override:
        return override.lower()
    if is_cloud_uri(path):
        ext = os.path.splitext(path.split("?")[0])[1].lstrip(".").lower()
        if ext == "ndjson":
            return "jsonl"
        if ext in {"csv", "json", "jsonl", "parquet"}:
            return ext
        return None
    detected = detect_file_type(path)
    if detected.get("success"):
        return detected.get("datatype").id()
    return None


def _infer_fields(path: str, filetype: str) -> list[dict[str, Any]]:
    if filetype not in DUCKABLE_FILE_TYPES:
        raise ValueError(f"Unsupported file type for API discovery: {filetype}")
    rows = duckdb_decompose(filename=path, filetype=filetype, path="*", limit=10000)
    fields = []
    for row in rows:
        if len(row) < 2:
            continue
        field_name = row[0]
        field_type = str(row[1]).lower()
        fields.append({"name": field_name, "type": field_type})
    return fields


def _infer_primary_key_candidates(path: str, filetype: str) -> list[str]:
    if filetype not in DUCKABLE_FILE_TYPES:
        return []
    rows = duckdb_decompose(
        filename=path, filetype=filetype, path="*", limit=10000, use_summarize=True
    )
    candidates: list[str] = []
    for row in rows:
        if len(row) < 5:
            continue
        try:
            unique_count = int(row[3])
            total_count = int(row[4])
        except (TypeError, ValueError):
            continue
        if total_count > 0 and unique_count == total_count:
            candidates.append(row[0])
    return candidates


def _split_csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _json_safe_value(val) for key, val in row.items()}


def _duckdb_type_to_python(dtype: str) -> type:
    dtype = dtype.lower()
    if any(token in dtype for token in ("int", "bigint", "smallint", "tinyint", "hugeint")):
        return int
    if any(token in dtype for token in ("double", "float", "real", "decimal", "numeric")):
        return float
    if "bool" in dtype:
        return bool
    return str


def _model_name(resource_name: str, suffix: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]+", "_", resource_name).strip("_")
    if not safe:
        safe = "Resource"
    if safe[0].isdigit():
        safe = f"R_{safe}"
    return f"{safe}{suffix}"


def _create_row_model(resource_name: str, fields: list[dict[str, Any]]) -> type[BaseModel]:
    field_defs: dict[str, Any] = {}
    for field in fields:
        name = field.get("name")
        if not name:
            continue
        py_type = _duckdb_type_to_python(str(field.get("type", "varchar")))
        field_defs[name] = (Optional[py_type], Field(default=None, description=field.get("type")))  # noqa: UP045
    if not field_defs:
        field_defs["value"] = (Optional[Any], Field(default=None))  # noqa: UP045
    return create_model(_model_name(resource_name, "Row"), **field_defs)  # type: ignore[call-overload]


def _create_list_response_model(resource_name: str, row_model: type[BaseModel]) -> type[BaseModel]:
    return create_model(
        _model_name(resource_name, "ListResponse"),
        data=(list[row_model], Field(description="Matching records")),  # type: ignore[valid-type]
        pagination=(PaginationMeta, Field(description="Pagination metadata")),
    )


def _single_primary_key_field(primary_key: Any) -> str | None:
    if isinstance(primary_key, str):
        return primary_key
    if isinstance(primary_key, list) and len(primary_key) == 1:
        return primary_key[0]
    return None


def _apply_sort_alias(params: dict[str, str]) -> dict[str, str]:
    merged = dict(params)
    if "sort" in merged and "order_by" not in merged:
        sort_val = merged.pop("sort")
        if sort_val.startswith("-"):
            merged["order_by"] = sort_val[1:]
            merged["order_dir"] = "desc"
        else:
            merged["order_by"] = sort_val
            merged.setdefault("order_dir", "asc")
    return merged


def _build_filter_openapi_extra(
    fields: list[str], allowed_ops: list[str]
) -> dict[str, list[dict[str, Any]]]:
    parameters: list[dict[str, Any]] = []
    for field in sorted(fields):
        for op in sorted(allowed_ops):
            parameters.append(
                {
                    "name": f"{field}__{op}",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "string"},
                    "description": f"Filter where {field} {op} the given value.",
                }
            )
        parameters.append(
            {
                "name": field,
                "in": "query",
                "required": False,
                "schema": {"type": "string"},
                "description": f"Shorthand for {field}__eq.",
            }
        )
    return {"parameters": parameters}


API_CONFIG_JSON_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "undatum Data API config",
    "type": "object",
    "required": ["resources"],
    "properties": {
        "resources": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["name", "path", "format"],
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "path": {"type": "string", "minLength": 1},
                    "format": {
                        "type": "string",
                        "enum": ["csv", "json", "jsonl", "parquet"],
                    },
                    "read_only": {"type": "boolean"},
                    "primary_key": {
                        "oneOf": [
                            {"type": "string"},
                            {"type": "array", "items": {"type": "string"}},
                        ]
                    },
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name"],
                            "properties": {
                                "name": {"type": "string"},
                                "type": {"type": "string"},
                            },
                        },
                    },
                    "pagination": {
                        "type": "object",
                        "properties": {
                            "default_limit": {"type": "integer", "minimum": 1},
                            "max_limit": {"type": "integer", "minimum": 1},
                        },
                    },
                    "query": {
                        "type": "object",
                        "properties": {
                            "allowed_ops": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "allowed_order_by": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }
    },
}


def validate_api_config_schema(config: Any) -> None:
    """Validate an API config against the embedded JSON Schema subset.

    Raises:
        ValueError: If the config does not match the required shape.
    """
    if not isinstance(config, dict):
        raise ValueError("API config must be a JSON/YAML object.")
    resources = config.get("resources")
    if not isinstance(resources, list) or not resources:
        raise ValueError("API config must define a non-empty 'resources' array.")
    query_timeout = config.get("query_timeout")
    if query_timeout is not None and (
        isinstance(query_timeout, bool)
        or not isinstance(query_timeout, (int, float))
        or query_timeout < 0
    ):
        raise ValueError("query_timeout must be a non-negative number of seconds.")
    allowed_formats = {"csv", "json", "jsonl", "parquet"}
    for idx, resource in enumerate(resources, start=1):
        label = f"Resource {idx}"
        if not isinstance(resource, dict):
            raise ValueError(f"{label} must be an object.")
        name = resource.get("name") or f"resource_{idx}"
        label = f"Resource '{name}'"
        path = resource.get("path")
        fmt = resource.get("format")
        if not isinstance(path, str) or not path.strip():
            raise ValueError(f"{label} missing path.")
        if not isinstance(fmt, str) or fmt.lower() not in allowed_formats:
            raise ValueError(
                f"{label} has unsupported format '{fmt}'. Use csv, json, jsonl, or parquet."
            )
        fields = resource.get("fields")
        if fields is not None:
            if not isinstance(fields, list):
                raise ValueError(f"{label} fields must be an array.")
            for field in fields:
                if not isinstance(field, dict) or not field.get("name"):
                    raise ValueError(f"{label} field entries must be objects with a name.")
        pagination = resource.get("pagination")
        if pagination is not None and not isinstance(pagination, dict):
            raise ValueError(f"{label} pagination must be an object.")
        query = resource.get("query")
        if query is not None and not isinstance(query, dict):
            raise ValueError(f"{label} query must be an object.")


def _download_fsspec_uri(path: str, dest: str) -> None:
    """Copy a GCS/Azure/s3a object to a local file via fsspec."""
    try:
        import fsspec
    except ImportError as exc:
        raise missing_cloud_extra_error(path, exc) from exc
    try:
        fs, _, paths = fsspec.get_fs_token_paths(path)
        src_path = paths[0] if paths else path
        with fs.open(src_path, "rb") as src, open(dest, "wb") as out:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
    except Exception as exc:
        if looks_like_missing_cloud_dep(path, exc):
            raise missing_cloud_extra_error(path, exc) from exc
        raise


def _materialize_resource_path(path: str, temp_files: list[str]) -> str:
    """Return a local path DuckDB can read, downloading cloud URIs as needed."""
    if not is_cloud_uri(path):
        return path

    suffix = cloud_object_suffix(path)
    temp_fd, temp_path = tempfile.mkstemp(suffix=suffix)
    os.close(temp_fd)
    try:
        logger.info("Downloading %s for Data API", path)
        if is_s3_uri(path):
            from ..formats.s3 import get_s3_client, parse_s3_uri

            bucket, key = parse_s3_uri(path)
            client = get_s3_client()
            client.download_file(bucket, key, temp_path)
        else:
            _download_fsspec_uri(path, temp_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
    temp_files.append(temp_path)
    return temp_path


def load_api_config(path: str) -> dict[str, Any]:
    """Load API config from YAML or JSON."""
    with open(path, encoding="utf8") as handle:
        raw = handle.read()
    if path.lower().endswith(".json"):
        return json.loads(raw)
    return yaml.safe_load(raw)


def dump_api_config(
    config: dict[str, Any], output: str | None = None, config_format: str | None = None
) -> str:
    """Serialize API config to YAML or JSON."""
    if config_format:
        config_format = config_format.lower()
    if output and not config_format:
        config_format = "json" if output.lower().endswith(".json") else "yaml"
    if config_format == "json":
        return json.dumps(config, indent=2, ensure_ascii=False)
    return yaml.safe_dump(config, sort_keys=False, allow_unicode=False)


def _validate_resources_config(config: dict[str, Any], temp_files: list[str] | None = None) -> None:
    validate_api_config_schema(config)
    resources = config.get("resources") or []
    if temp_files is None:
        temp_files = []
    for idx, resource in enumerate(resources, start=1):
        name = resource.get("name") or f"resource_{idx}"
        path = resource.get("path")
        fmt = resource.get("format")
        if not path or not fmt:
            raise ValueError(f"Resource {name} missing path or format.")
        if is_uri(path) and not is_cloud_uri(path):
            raise ValueError(
                f"Resource {name} path '{path}' is not a local file or cloud URI "
                f"(s3://, gs://, gcs://, az://, abfs://, abfss://)."
            )
        try:
            validate_file_path(path, check_read=True)
        except FileNotFoundError as exc:
            suggestions = find_similar_files(path)
            raise FileNotFoundError(path, suggestions) from exc
        except PermissionError as exc:
            raise PermissionError(path, operation="read") from exc
        resource["path"] = _materialize_resource_path(path, temp_files)


def _build_api_app(
    config: dict[str, Any],
    *,
    api_key: str | None = None,
    cors_origins: list[str] | None = None,
    query_timeout: float | None = None,
):
    """Build the FastAPI app; imports the optional ``api`` extra only when called."""
    require_api_dependencies()
    from .api_app import build_api_app

    return build_api_app(
        config, api_key=api_key, cors_origins=cors_origins, query_timeout=query_timeout
    )


def _print_startup_banner(host: str, port: int, resource_summaries: list[dict[str, Any]]) -> None:
    from rich.console import Console
    from rich.panel import Panel

    base = f"http://{host}:{port}"
    lines = [f"[bold]Base URL:[/bold] {base}", "", "[bold]Resources:[/bold]"]
    for resource in resource_summaries:
        lines.append(f"  GET {base}{resource['list']}")
        if resource.get("detail"):
            lines.append(f"  GET {base}{resource['detail']}")
    lines.extend(
        [
            "",
            "[bold]Documentation:[/bold]",
            f"  Swagger UI: {base}/docs",
            f"  ReDoc:      {base}/redoc",
            f"  OpenAPI:    {base}/openapi.json",
        ]
    )
    Console().print(Panel("\n".join(lines), title="undatum Data API", border_style="green"))


class DataApi:
    """Data API command handler."""

    def discover(
        self, input_files: list[str], options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Build a Data API configuration with one resource per input file.

        Args:
            input_files: Data files to expose.
            options: CLI options (``output``, ``emit``, ``format_in``, ``config_format``...).

        Returns:
            The configuration; it is also written to ``output`` and/or printed when
            ``emit`` is true.

        Raises:
            ValueError: If no input files are given.
        """
        if options is None:
            options = {}
        if not input_files:
            raise ValueError("No input files provided.")

        output = get_option(options, "output")
        emit = get_option(options, "emit")
        if emit is None:
            emit = True
        format_in = get_option(options, "format_in")
        config_format = get_option(options, "config_format")
        default_limit = get_option(options, "default_limit") or DEFAULT_PAGINATION["default_limit"]
        max_limit = get_option(options, "max_limit") or DEFAULT_PAGINATION["max_limit"]
        allowed_ops = _split_csv(get_option(options, "allowed_ops")) or DEFAULT_ALLOWED_OPS

        resources = []
        used_names: set[str] = set()
        for idx, path in enumerate(input_files, start=1):
            try:
                validate_file_path(path, check_read=True)
            except FileNotFoundError as exc:
                suggestions = find_similar_files(path)
                raise FileNotFoundError(path, suggestions) from exc
            except PermissionError as exc:
                raise PermissionError(path, operation="read") from exc

            if is_uri(path):
                abs_path = path
            else:
                abs_path = os.path.abspath(path)
            filetype = _detect_format(abs_path, format_in)
            if not filetype:
                from ..common.errors import FormatError

                supported = ["csv", "json", "jsonl", "parquet"]
                raise FormatError(abs_path, "unknown", supported)
            infer_temps: list[str] = []
            infer_path = abs_path
            if is_cloud_uri(abs_path):
                infer_path = _materialize_resource_path(abs_path, infer_temps)
            try:
                fields = _infer_fields(infer_path, filetype)
                primary_candidates = _infer_primary_key_candidates(infer_path, filetype)
            finally:
                for tmp in infer_temps:
                    if os.path.exists(tmp):
                        os.remove(tmp)
            base_name = _normalize_resource_name(abs_path, idx)
            resource_name = _unique_resource_name(base_name, used_names)
            if resource_name != base_name:
                logger.warning(
                    "Resource name collision for %s: using '%s' instead of '%s'",
                    abs_path,
                    resource_name,
                    base_name,
                )
                sys.stderr.write(
                    f"Warning: resource name collision; using '{resource_name}' for {abs_path}\n"
                )
            resource = {
                "name": resource_name,
                "path": abs_path,
                "format": filetype,
                "read_only": True,
                "fields": fields,
                "pagination": {
                    "default_limit": int(default_limit),
                    "max_limit": int(max_limit),
                },
                "query": {
                    "allowed_ops": allowed_ops,
                    "allowed_order_by": [field["name"] for field in fields],
                },
            }
            if primary_candidates:
                resource["primary_key"] = primary_candidates[0]
            resources.append(resource)

        config = {"resources": resources}
        validate_api_config_schema(config)
        payload = dump_api_config(config, output=output, config_format=config_format)
        if output:
            with open(output, "w", encoding="utf8") as handle:
                handle.write(payload)
                handle.write("\n")
        elif emit:
            sys.stdout.write(payload)
            sys.stdout.write("\n")
        return config

    def serve(
        self,
        config_path: str | None,
        options: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        """Serve the Data API with uvicorn until interrupted.

        Args:
            config_path: YAML/JSON configuration file (ignored when ``config`` is given).
            options: ``host``, ``port``, ``api_key``, ``cors_origins``, ``query_timeout``.
            config: Configuration built in memory, e.g. by :meth:`discover`.

        Raises:
            ValueError: If neither ``config_path`` nor ``config`` is given.
        """
        if options is None:
            options = {}
        require_api_dependencies()
        import uvicorn  # type: ignore

        if config is None:
            if not config_path:
                raise ValueError("Config path is required.")
            config = load_api_config(config_path)

        host = get_option(options, "host") or "127.0.0.1"
        port = int(get_option(options, "port") or 8000)
        api_key = get_option(options, "api_key") or os.environ.get("UNDATUM_API_KEY")
        cors_raw = get_option(options, "cors_origins")
        cors_origins = _split_csv(cors_raw) if cors_raw else []
        query_timeout = get_option(options, "query_timeout")

        app = _build_api_app(
            config,
            api_key=api_key,
            cors_origins=cors_origins or None,
            query_timeout=float(query_timeout) if query_timeout is not None else None,
        )
        resource_summaries = getattr(app.state, "resource_summaries", [])
        _print_startup_banner(host, port, resource_summaries)
        uvicorn.run(app, host=host, port=port, log_level="info", access_log=True)

    def run(self, input_files: list[str], options: dict[str, Any] | None = None) -> None:
        """Discover a configuration for ``input_files`` and serve it immediately."""
        if options is None:
            options = {}
        options = dict(options)
        options["emit"] = False
        config = self.discover(input_files, options)
        self.serve(None, options, config=config)

    def export_openapi(
        self, config_path: str, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Return the OpenAPI schema of a configuration, optionally writing it to a file.

        Args:
            config_path: Data API configuration file.
            options: ``output`` path and ``format`` (``json`` or ``yaml``).

        Returns:
            The OpenAPI schema as a dict.
        """
        if options is None:
            options = {}
        require_api_dependencies()

        config = load_api_config(config_path)
        app = _build_api_app(config)
        schema = app.openapi()

        output = get_option(options, "output")
        schema_format = get_option(options, "format")
        if output and not schema_format:
            schema_format = "yaml" if output.lower().endswith((".yml", ".yaml")) else "json"
        schema_format = (schema_format or "json").lower()

        if schema_format == "yaml":
            payload = yaml.safe_dump(schema, sort_keys=False, allow_unicode=False)
        else:
            payload = json.dumps(schema, indent=2, ensure_ascii=False)

        if output:
            with open(output, "w", encoding="utf8") as handle:
                handle.write(payload)
                if not payload.endswith("\n"):
                    handle.write("\n")
        else:
            sys.stdout.write(payload)
            if not payload.endswith("\n"):
                sys.stdout.write("\n")
        return schema
