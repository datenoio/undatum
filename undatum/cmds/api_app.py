"""FastAPI application builder for the Data API.

This module imports FastAPI and Starlette at module level, so it must only be
imported when the Data API actually runs (``undatum api serve|run|openapi``).
The command module :mod:`undatum.cmds.api` imports it lazily, which keeps the
base install (without the ``api`` extra) importable.
"""

from __future__ import annotations

import hmac
import threading
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .. import __version__
from .api import (
    DEFAULT_ALLOWED_OPS,
    DEFAULT_ORDER_DIRS,
    DEFAULT_PAGINATION,
    DEFAULT_QUERY_TIMEOUT,
    OPERATOR_MAP,
    RESERVED_QUERY_PARAMS,
    _apply_sort_alias,
    _build_filter_openapi_extra,
    _create_list_response_model,
    _create_row_model,
    _json_safe_row,
    _single_primary_key_field,
    _validate_resources_config,
)

PUBLIC_PATHS = {"/docs", "/redoc", "/openapi.json"}


def build_api_app(
    config: dict[str, Any],
    *,
    api_key: str | None = None,
    cors_origins: list[str] | None = None,
    query_timeout: float | None = None,
) -> FastAPI:
    """Build the read-only FastAPI app for the resources in ``config``.

    Args:
        config: Validated API config with a ``resources`` list.
        api_key: When set, every non-docs request must send it in ``X-API-Key``.
        cors_origins: Allowed CORS origins; CORS is disabled when empty.
        query_timeout: Seconds before a DuckDB query is interrupted (HTTP 504).
            Defaults to ``config["query_timeout"]`` or ``DEFAULT_QUERY_TIMEOUT``;
            ``0`` disables the timeout.

    Returns:
        The configured FastAPI application.
    """
    temp_files: list[str] = []
    _validate_resources_config(config, temp_files)
    if query_timeout is None:
        query_timeout = float(config.get("query_timeout", DEFAULT_QUERY_TIMEOUT))

    app = FastAPI(
        title="undatum Data API",
        description="Read-only HTTP API over file-backed datasets (CSV, JSON/JSONL, Parquet).",
        version=__version__,
    )
    app.state.temp_files = temp_files

    if cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "OPTIONS"],
            allow_headers=["*"],
        )

    if api_key:
        expected = api_key.encode("utf8")

        class APIKeyMiddleware(BaseHTTPMiddleware):
            async def dispatch(self, request: Request, call_next):
                path = request.url.path
                if path in PUBLIC_PATHS or path.startswith("/docs"):
                    return await call_next(request)
                provided = request.headers.get("x-api-key") or ""
                if not hmac.compare_digest(provided.encode("utf8"), expected):
                    return JSONResponse({"detail": "Unauthorized"}, status_code=401)
                return await call_next(request)

        app.add_middleware(APIKeyMiddleware)

    conn = duckdb.connect(database=":memory:")
    resource_index: dict[str, dict[str, Any]] = {}
    resource_summaries: list[dict[str, Any]] = []

    resources = config.get("resources") or []
    for idx, resource in enumerate(resources, start=1):
        name = resource.get("name") or f"resource_{idx}"
        path = resource.get("path")
        fmt = resource.get("format")
        if not path or not fmt:
            raise ValueError(f"Resource {name} missing path or format.")

        table_name = f"resource_{idx}"
        safe_path = path.replace("'", "''")
        if fmt == "csv":
            read_expr = f"read_csv_auto('{safe_path}')"
        elif fmt in {"json", "jsonl"}:
            read_expr = f"read_json_auto('{safe_path}')"
        elif fmt == "parquet":
            read_expr = f"read_parquet('{safe_path}')"
        else:
            raise ValueError(f"Unsupported API format: {fmt}")
        conn.execute(f'CREATE OR REPLACE VIEW "{table_name}" AS SELECT * FROM {read_expr}')

        field_defs = resource.get("fields") or []
        fields = [field.get("name") for field in field_defs if field.get("name")]
        allowed_ops = resource.get("query", {}).get("allowed_ops") or DEFAULT_ALLOWED_OPS
        allowed_order_by = resource.get("query", {}).get("allowed_order_by") or fields
        pagination = resource.get("pagination") or DEFAULT_PAGINATION
        primary_key = resource.get("primary_key")
        meta = {
            "name": name,
            "table": table_name,
            "fields": set(fields),
            "allowed_ops": set(allowed_ops),
            "allowed_order_by": set(allowed_order_by),
            "pagination": pagination,
            "default_limit": int(
                pagination.get("default_limit", DEFAULT_PAGINATION["default_limit"])
            ),
            "max_limit": int(pagination.get("max_limit", DEFAULT_PAGINATION["max_limit"])),
            "primary_key": primary_key,
            "row_model": _create_row_model(name, field_defs),
            "list_model": None,
        }
        meta["list_model"] = _create_list_response_model(name, meta["row_model"])
        resource_index[name] = meta
        pk_field = _single_primary_key_field(primary_key)
        resource_summaries.append(
            {
                "name": name,
                "list": f"/{name}",
                "detail": f"/{name}/{{pk}}" if pk_field else None,
                "primary_key": pk_field,
            }
        )

    def _execute(sql: str, values: list[Any], *, one: bool = False):
        """Run a query on a per-request cursor, interrupting it after the timeout."""
        cursor = conn.cursor()
        timer = threading.Timer(query_timeout, cursor.interrupt) if query_timeout else None
        try:
            if timer:
                timer.start()
            result = cursor.execute(sql, values)
            columns = [col[0] for col in result.description]
            rows = [result.fetchone()] if one else result.fetchall()
            return columns, rows
        except duckdb.InterruptException as exc:
            raise HTTPException(status_code=504, detail="Query timed out") from exc
        finally:
            if timer:
                timer.cancel()
            cursor.close()

    def _parse_query(
        resource_meta: dict[str, Any], params: dict[str, str]
    ) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        values: list[Any] = []
        for key, value in params.items():
            if key in RESERVED_QUERY_PARAMS:
                continue
            if "__" in key:
                field, op = key.split("__", 1)
            else:
                field, op = key, "eq"
            if field not in resource_meta["fields"]:
                raise HTTPException(status_code=400, detail=f"Unknown field: {field}")
            if op not in resource_meta["allowed_ops"]:
                raise HTTPException(status_code=400, detail=f"Unsupported operator: {op}")
            clauses.append(f'"{field}" {OPERATOR_MAP[op]} ?')
            values.append(value)
        return " AND ".join(clauses), values

    def _apply_order(
        sql: str, order_by: str | None, order_dir: str, resource_meta: dict[str, Any]
    ) -> str:
        if not order_by:
            return sql
        order_fields = [part.strip() for part in order_by.split(",") if part.strip()]
        if not order_fields:
            return sql
        for field in order_fields:
            if field not in resource_meta["allowed_order_by"]:
                raise HTTPException(status_code=400, detail=f"Order by not allowed: {field}")
        dir_lower = order_dir.lower()
        if dir_lower not in DEFAULT_ORDER_DIRS:
            raise HTTPException(status_code=400, detail=f"Invalid order_dir: {order_dir}")
        order_clause = ", ".join(f'"{field}" {dir_lower.upper()}' for field in order_fields)
        return f"{sql} ORDER BY {order_clause}"

    def _count_rows(resource_meta: dict[str, Any], params: dict[str, str]) -> int:
        where_clause, values = _parse_query(resource_meta, params)
        sql = f'SELECT COUNT(*) FROM "{resource_meta["table"]}"'
        if where_clause:
            sql = f"{sql} WHERE {where_clause}"
        _, rows = _execute(sql, values, one=True)
        return int(rows[0][0]) if rows and rows[0] else 0

    def _handle_list(resource_meta: dict[str, Any], params: dict[str, str]) -> dict[str, Any]:
        params = _apply_sort_alias(params)
        default_limit = resource_meta["default_limit"]
        max_limit = resource_meta["max_limit"]

        try:
            limit = int(params.get("limit", default_limit))
            offset = int(params.get("offset", 0))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="limit/offset must be integers") from exc

        include_total = params.get("include_total", "").lower() in {"1", "true", "yes"}

        limit = min(limit, max_limit)
        if limit < 0 or offset < 0:
            raise HTTPException(status_code=400, detail="limit/offset must be >= 0")

        sql = f'SELECT * FROM "{resource_meta["table"]}"'
        where_clause, values = _parse_query(resource_meta, params)
        if where_clause:
            sql = f"{sql} WHERE {where_clause}"
        sql = _apply_order(
            sql, params.get("order_by"), params.get("order_dir", "asc"), resource_meta
        )
        sql = f"{sql} LIMIT ? OFFSET ?"
        values.extend([limit, offset])

        columns, raw_rows = _execute(sql, values)
        rows = [_json_safe_row(dict(zip(columns, row, strict=False))) for row in raw_rows]

        pagination_meta: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "count": len(rows),
        }
        if include_total:
            pagination_meta["total"] = _count_rows(resource_meta, params)

        return {"data": rows, "pagination": pagination_meta}

    def _handle_detail(resource_meta: dict[str, Any], pk_value: str) -> dict[str, Any]:
        field = _single_primary_key_field(resource_meta["primary_key"])
        if not field:
            raise HTTPException(status_code=404, detail="Primary key endpoint not available")
        if field not in resource_meta["fields"]:
            raise HTTPException(status_code=404, detail="Primary key field not available")

        sql = f'SELECT * FROM "{resource_meta["table"]}" WHERE "{field}" = ? LIMIT 1'
        columns, rows = _execute(sql, [pk_value], one=True)
        if not rows or rows[0] is None:
            raise HTTPException(status_code=404, detail="Not found")
        return _json_safe_row(dict(zip(columns, rows[0], strict=False)))

    @app.get("/", tags=["meta"], summary="API discovery")
    def api_root() -> dict[str, Any]:
        return {
            "name": "undatum Data API",
            "version": __version__,
            "docs": "/docs",
            "openapi": "/openapi.json",
            "resources": resource_summaries,
        }

    def _make_list_handler(resource_meta: dict[str, Any]):
        # Bind per-resource limits here; closing over loop variables would give every
        # route the limits of the last resource.
        default_limit = resource_meta["default_limit"]
        max_limit = resource_meta["max_limit"]

        # A sync handler: FastAPI runs it in a threadpool, so slow DuckDB queries do
        # not block the event loop.
        def list_handler(
            request: Request,
            limit: int | None = Query(
                default=None,
                ge=0,
                le=max_limit,
                description=f"Page size (default {default_limit}, max {max_limit}).",
            ),
            offset: int = Query(default=0, ge=0, description="Number of rows to skip."),
            order_by: str | None = Query(
                default=None, description="Comma-separated fields to sort by."
            ),
            order_dir: str = Query(default="asc", description="Sort direction: asc or desc."),
            sort: str | None = Query(
                default=None,
                description="Sort alias: field name, or prefix with - for descending.",
            ),
            include_total: bool = Query(
                default=False,
                description="Include total matching row count (may be slower).",
            ),
        ):
            params = {
                key: value
                for key, value in request.query_params.items()
                if key not in RESERVED_QUERY_PARAMS
            }
            params["limit"] = str(limit if limit is not None else default_limit)
            params["offset"] = str(offset)
            if order_by is not None:
                params["order_by"] = order_by
            params["order_dir"] = order_dir
            if sort is not None:
                params["sort"] = sort
            params["include_total"] = "true" if include_total else "false"
            return _handle_list(resource_meta, params)

        return list_handler

    def _make_detail_handler(resource_meta: dict[str, Any]):
        def detail_handler(pk: str):
            return _handle_detail(resource_meta, pk)

        return detail_handler

    for resource_name, meta in resource_index.items():
        route_path = f"/{resource_name}"
        openapi_extra = _build_filter_openapi_extra(
            sorted(meta["fields"]), sorted(meta["allowed_ops"])
        )
        app.get(
            route_path,
            response_model=meta["list_model"],
            tags=[resource_name],
            summary=f"List {resource_name} records",
            openapi_extra=openapi_extra,
        )(_make_list_handler(meta))

        if _single_primary_key_field(meta.get("primary_key")):
            app.get(
                f"{route_path}/{{pk}}",
                response_model=meta["row_model"],
                tags=[resource_name],
                summary=f"Get a single {resource_name} record by primary key",
            )(_make_detail_handler(meta))

    app.state.resource_summaries = resource_summaries
    return app
