"""Unified database source handling backed by iterabledata DB engines.

Routes database connection URIs to the read-only database drivers provided by
``iterabledata`` (PostgreSQL, MySQL/MariaDB, MS SQL Server, ClickHouse, MongoDB,
Elasticsearch/OpenSearch). This lets undatum read commands consume a database
source the same way they consume files, and lets ``db query`` reach engines that
have no native undatum connection layer.

Driver-specific options can be supplied through the URI query string, e.g.::

    clickhouse://host:9000/db?query=SELECT * FROM events LIMIT 100
    mongodb://host:27017/mydb?collection=users&limit=1000
    elasticsearch://host:9200?index=logs

Recognized query params are forwarded to the iterabledata driver and stripped
from the connection URI; any other params are left intact.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from iterable.helpers.detect import open_iterable

# URI scheme -> iterabledata engine name.
DB_URI_SCHEMES: dict[str, str] = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "mssql": "mssql",
    "sqlserver": "mssql",
    "clickhouse": "clickhouse",
    "mongodb": "mongo",
    "mongo": "mongo",
    "elasticsearch": "elasticsearch",
    "opensearch": "elasticsearch",
}

# iterabledata engine -> undatum extra that installs its driver.
ENGINE_EXTRAS: dict[str, str] = {
    "postgres": "postgres",
    "mysql": "mysql",
    "mssql": "mssql",
    "clickhouse": "clickhouse",
    "elasticsearch": "elastic",
}

# Engines without a native undatum connection layer; ``db query`` must route
# these through iterabledata's drivers.
ITERABLE_ONLY_DB_ENGINES = frozenset({"mssql", "clickhouse", "mongo", "elasticsearch"})

# Query-string params consumed by undatum and forwarded as driver kwargs instead
# of remaining part of the connection URI.
_LIST_PARAMS = frozenset({"columns"})
_INT_PARAMS = frozenset({"limit", "batch_size", "size", "skip"})
_DRIVER_KWARG_PARAMS = frozenset(
    {
        "query",
        "table",
        "collection",
        "database",
        "index",
        "columns",
        "filter",
        "projection",
        "limit",
        "batch_size",
        "size",
        "skip",
    }
)


def detect_db_engine(uri: str) -> str | None:
    """Return the iterabledata engine name for a DB URI, or None if not a DB URI."""
    if not uri or not isinstance(uri, str) or "://" not in uri:
        return None
    scheme = uri.split("://", 1)[0].lower()
    return DB_URI_SCHEMES.get(scheme)


def is_db_uri(uri: str) -> bool:
    """Return True if the URI scheme maps to a known iterabledata DB engine."""
    return detect_db_engine(uri) is not None


def _split_driver_kwargs(uri: str) -> tuple[str, dict[str, Any]]:
    """Pull undatum-consumed driver kwargs out of the URI query string.

    Returns the connection URI without the consumed params plus a kwargs dict.
    """
    parsed = urlparse(uri)
    if not parsed.query:
        return uri, {}
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    driver_kwargs: dict[str, Any] = {}
    remaining: list[tuple[str, str]] = []
    for key, value in pairs:
        if key in _DRIVER_KWARG_PARAMS:
            if key in _LIST_PARAMS:
                driver_kwargs[key] = [c for c in value.split(",") if c]
            elif key in _INT_PARAMS:
                try:
                    driver_kwargs[key] = int(value)
                except ValueError:
                    driver_kwargs[key] = value
            else:
                driver_kwargs[key] = value
        else:
            remaining.append((key, value))
    clean_uri = urlunparse(parsed._replace(query=urlencode(remaining)))
    return clean_uri, driver_kwargs


def open_db_source(
    uri: str,
    *,
    query: str | None = None,
    iterableargs: dict[str, Any] | None = None,
    **kwargs: Any,
) -> Any:
    """Open a database URI as an iterable via iterabledata's DB drivers.

    Args:
        uri: Database connection URI (scheme must be a known DB engine).
        query: Optional SQL query (or table name) forwarded as the driver
            ``query`` kwarg, overriding any ``query`` in the URI.
        iterableargs: Extra driver kwargs.
        **kwargs: Additional driver kwargs (highest precedence).

    Returns:
        A ``DatabaseIterable`` yielding dict rows; supports iteration, context
        management, and ``close()``.

    Raises:
        ValueError: If the URI scheme is not a recognized database engine.
        DependencyError: If the database driver is not installed.
    """
    engine = detect_db_engine(uri)
    if engine is None:
        raise ValueError(f"Not a recognized database URI: {uri!r}")
    clean_uri, driver_kwargs = _split_driver_kwargs(uri)
    if iterableargs:
        driver_kwargs.update(iterableargs)
    if kwargs:
        driver_kwargs.update(kwargs)
    if query is not None:
        driver_kwargs["query"] = query
    try:
        return open_iterable(clean_uri, engine=engine, iterableargs=driver_kwargs)
    except ImportError as exc:
        from .errors import DependencyError

        extra = ENGINE_EXTRAS.get(engine)
        raise DependencyError(
            exc.name or engine,
            feature=f"{engine} database URIs",
            install_command=f'pip install "undatum[{extra}]"' if extra else None,
        ) from exc
