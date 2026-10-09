"""Shared helpers for command modules.

Centralizes logic that was previously duplicated across the ``undatum.cmds``
modules: iterable option extraction and the DuckDB-with-iterable-fallback
execution pattern.
"""

import logging
import os
from collections.abc import Callable, Iterable, Iterator
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_EXCEL_FORMATS = {"xlsx", "xls", "ods"}
_CODEC_PROFILES = ("fast", "balanced", "max")
_WRITE_MODES = ("append", "overwrite", "error", "ignore", "create")
_ON_ERROR_POLICIES = ("raise", "skip", "warn")

ITERABLE_OPTIONS_KEYS = [
    "tagname",
    "delimiter",
    "quotechar",
    "encoding",
    "start_line",
    "page",
    "start_page",
    "prefix_strip",
    "table",
    "sheet",
    "trust",
    "on_error",
    "error_log",
]


def resolve_csv_delimiter(
    iterableargs: dict | None = None,
    *,
    filename: str | None = None,
    filetype: str | None = None,
) -> str | None:
    """Resolve CSV/TSV delimiter from explicit options or auto-detection.

    Args:
        iterableargs: Iterable reader options (may include ``delimiter``, ``encoding``).
        filename: Path used for auto-detection when delimiter is not set.
        filetype: Optional file type hint (``csv``, ``tsv``, ...).

    Returns:
        Delimiter character, or ``None`` when the source is not CSV-like.
    """
    iterableargs = iterableargs or {}
    delimiter = iterableargs.get("delimiter")
    if delimiter:
        return str(delimiter)

    from .format_names import format_from_name

    named = format_from_name(filename.split("?")[0]) if filename else None
    named_format = named[0] if named else None
    if not filename or (filetype or named_format) not in ("csv", "tsv"):
        return None

    if "tsv" in (filetype, named_format):
        return "\t"

    import os

    if not os.path.isfile(filename):
        return None

    from ..utils import detect_delimiter

    encoding = iterableargs.get("encoding") or "utf8"
    return detect_delimiter(filename, encoding=encoding)


def apply_iterable_csv_delimiter(
    iterable: Any, filename: str | None, iterableargs: dict | None
) -> None:
    """Apply CSV delimiter and quotechar on an open iterable.

    ``iterabledata.open_iterable`` passes these via ``options=``, but
    ``CSVIterable`` only reads them from constructor kwargs. This sets the
    attributes after open and re-initializes the reader.
    """
    iterableargs = iterableargs or {}
    changed = False
    if hasattr(iterable, "delimiter"):
        delimiter = resolve_csv_delimiter(iterableargs, filename=filename)
        if delimiter and getattr(iterable, "delimiter", None) != delimiter:
            iterable.delimiter = delimiter
            changed = True
    quotechar = iterableargs.get("quotechar")
    if (
        quotechar
        and hasattr(iterable, "quotechar")
        and getattr(iterable, "quotechar", None) != quotechar
    ):
        iterable.quotechar = quotechar
        changed = True
    if changed and hasattr(iterable, "reset"):
        iterable.reset()


def duckdb_read_csv_options(
    delimiter: str | None = None, *, ignore_errors: bool = True, all_varchar: bool = False
) -> str:
    """Build DuckDB ``read_csv`` option suffix (leading comma included)."""
    parts: list[str] = []
    if ignore_errors:
        parts.append("ignore_errors=true")
    if all_varchar:
        parts.append("all_varchar=true")
    if delimiter:
        escaped = delimiter.replace("\\", "\\\\").replace("'", "''")
        parts.append(f"delim='{escaped}'")
        # RFC 4180: a quote inside a quoted field is written twice.
        parts.append("quote='\"'")
        parts.append("escape='\"'")
        parts.append("strict_mode=false")
    if not parts:
        return ""
    return ", " + ", ".join(parts)


def duckdb_read_csv_expr(
    filename: str,
    delimiter: str | None = None,
    *,
    ignore_errors: bool = True,
    sample_size: int | None = None,
    all_varchar: bool = False,
) -> str:
    """Build a DuckDB ``read_csv('path', ...)`` expression."""
    escaped = filename.replace("'", "''")
    opts = duckdb_read_csv_options(delimiter, ignore_errors=ignore_errors, all_varchar=all_varchar)
    if sample_size is not None:
        opts += f", sample_size={sample_size}"
    return f"read_csv('{escaped}'{opts})"


def duckdb_read_expr(
    filename: str,
    filetype: str | None = None,
    iterableargs: dict | None = None,
    *,
    all_varchar: bool = False,
) -> str:
    """Build a DuckDB read expression for CSV, JSON, or Parquet files."""
    from ..utils import get_file_type

    source_type = filetype or get_file_type(filename) or "csv"
    iterableargs = iterableargs or {}

    if source_type == "csv":
        delimiter = resolve_csv_delimiter(iterableargs, filename=filename, filetype=source_type)
        return duckdb_read_csv_expr(filename, delimiter, all_varchar=all_varchar)
    if source_type in ("json", "jsonl"):
        escaped = filename.replace("'", "''")
        return f"read_json_auto('{escaped}')"
    if source_type == "parquet":
        escaped = filename.replace("'", "''")
        return f"read_parquet('{escaped}')"
    raise ValueError(f"Unsupported file type for DuckDB: {source_type}")


def quote_sql_identifier(name: str) -> str:
    """Quote a SQL identifier for DuckDB."""
    name = name.strip()
    if name.startswith('"') and name.endswith('"'):
        return name
    escaped = name.replace('"', '""')
    return f'"{escaped}"'


def get_iterable_options(options: dict) -> dict:
    """Extract iterable-specific options from options dictionary.

    Maps ``start_page`` (undatum CLI name) to ``page`` (iterabledata name) and
    ``sheet`` to ``table``. Named table/sheet resolution against the source file
    is done separately by :func:`apply_table_selection`.

    Args:
        options: Full command options dictionary.

    Returns:
        Dictionary with only the keys consumed by ``iterabledata`` readers.
    """
    from .app_config import get_cli_defaults

    cli_defaults = get_cli_defaults()
    out = {}
    for k in ITERABLE_OPTIONS_KEYS:
        if k in options and options[k] is not None:
            out[k] = options[k]
        elif k in cli_defaults and cli_defaults[k] is not None:
            out[k] = cli_defaults[k]
    if "start_page" in out and "page" not in out:
        out["page"] = out.pop("start_page")
    elif "start_page" in out:
        del out["start_page"]
    if "sheet" in out and "table" not in out:
        out["table"] = out.pop("sheet")
    elif "sheet" in out:
        del out["sheet"]
    if "on_error" in out:
        validated = validate_on_error(out["on_error"])
        if validated:
            out["on_error"] = validated
        else:
            del out["on_error"]
    if "quotechar" in out:
        quotechar = str(out["quotechar"])
        if len(quotechar) != 1:
            from .errors import ValidationError

            raise ValidationError(
                f"quotechar must be a single character, got {quotechar!r}.",
                field="quotechar",
            )
        out["quotechar"] = quotechar
    # --format-in (``filetype`` in older call sites) tells the reader which format to use.
    format_in = options.get("format_in") or options.get("filetype")
    if format_in and "format" not in out:
        out["format"] = str(format_in).lower()
    return out


def apply_table_selection(filename: str | None, iterableargs: dict | None) -> dict:
    """Resolve ``table`` / sheet names to iterabledata ``page`` or ``table``.

    Excel/ODS sheets are opened by ``page`` index. SQLite, lakehouse, and other
    multi-table formats keep the table name. Unknown names raise
    :class:`~undatum.common.errors.ValidationError` with available tables.

    Args:
        filename: Source path used to list tables (skipped for URIs/directories).
        iterableargs: Reader options, possibly including ``table``.

    Returns:
        A new options dict with ``table`` rewritten to ``page`` or left as a name.
    """
    from .errors import ValidationError

    args = dict(iterableargs or {})
    table = args.pop("table", None)
    if not table:
        return args

    tables = _list_source_tables(filename)
    if tables:
        if table not in tables:
            raise ValidationError(
                f"Unknown table or sheet {table!r}.",
                field="table",
                suggestions=list(tables),
            )
        fmt = _source_format_id(filename)
        if fmt in _EXCEL_FORMATS:
            args["page"] = tables.index(table)
        else:
            args["table"] = table
        return args

    args["table"] = table
    return args


def force_iterable_if_table(options: dict | None, engine: str) -> str:
    """Use the iterable engine when DuckDB would ignore reader options.

    DuckDB file scans do not honor iterabledata table/sheet selection,
    ``on_error`` skip/warn policies, a custom CSV ``quotechar``, or
    ``flatten_nested`` row projection.
    """
    options = options or {}
    if any(options.get(key) for key in ("table", "sheet", "table2", "sheet2")):
        return "iterable"
    on_error = options.get("on_error")
    if on_error and str(on_error).strip().lower() in ("skip", "warn"):
        return "iterable"
    if options.get("error_log"):
        return "iterable"
    if options.get("quotechar"):
        return "iterable"
    if options.get("flatten_nested"):
        return "iterable"
    return engine


def get_side_iterable_options(options: dict | None, side: int = 1) -> dict:
    """Iterable reader options for one side of a two-file command.

    Side 1 uses ``table`` / ``sheet`` / ``start_page``. Side 2 uses
    ``table2`` / ``sheet2`` / ``start_page2`` and does not inherit the first
    file's table selection.
    """
    options = dict(options or {})
    if side == 2:
        options["table"] = options.get("table2")
        options["sheet"] = options.get("sheet2")
        options["start_page"] = options.get("start_page2")
    return get_iterable_options(options)


def list_source_tables(filename: str | None) -> list[str] | None:
    """Return table/sheet names for a multi-table source, or None.

    Unlike :func:`apply_table_selection`, this also attempts URIs and
    directory-backed lakehouse sources.
    """
    if not filename:
        return None
    try:
        from iterable.ai.fileinfo import list_tables

        tables = list_tables(filename)
    except Exception:  # noqa: BLE001 - listing is best-effort
        return None
    if not tables:
        return None
    return list(tables)


def _list_source_tables(filename: str | None) -> list[str] | None:
    """Return table/sheet names for a local multi-table file, or None."""
    if not filename or "://" in str(filename) or not os.path.isfile(filename):
        return None
    return list_source_tables(filename)


def _source_format_id(filename: str | None) -> str | None:
    if not filename:
        return None
    try:
        from iterable.helpers.detect import detect_file_type

        info: Any = detect_file_type(filename)
        if info.get("success") and info.get("datatype") is not None:
            datatype = info["datatype"]
            if hasattr(datatype, "id") and callable(datatype.id):
                return str(datatype.id())
    except Exception:  # noqa: BLE001
        return None
    return None


def parse_column_list(value: str | None) -> list[str] | None:
    """Parse a comma-separated column list. Empty/None returns None."""
    if not value or not str(value).strip():
        return None
    columns = [part.strip() for part in str(value).split(",") if part.strip()]
    return columns or None


def parse_row_range(value: str | None) -> tuple[int, int] | None:
    """Parse ``START:END`` into a half-open integer range.

    Raises:
        ValidationError: If the value is not ``START:END`` with integers.
    """
    from .errors import ValidationError

    if not value or not str(value).strip():
        return None
    raw = str(value).strip()
    if ":" not in raw:
        raise ValidationError(
            "Row range must be START:END (e.g. 0:1000).",
            field="row_range",
        )
    start_s, end_s = raw.split(":", 1)
    try:
        start = int(start_s.strip())
        end = int(end_s.strip())
    except ValueError as exc:
        raise ValidationError(
            "Row range START and END must be integers (e.g. 0:1000).",
            field="row_range",
        ) from exc
    if start < 0 or end < start:
        raise ValidationError(
            "Row range must satisfy 0 <= START <= END.",
            field="row_range",
        )
    return start, end


def validate_codec_profile(profile: str | None) -> str | None:
    """Return a normalized codec profile or None.

    Raises:
        ValidationError: If profile is set but not fast/balanced/max.
    """
    from .errors import ValidationError

    if not profile:
        return None
    normalized = str(profile).strip().lower()
    if normalized not in _CODEC_PROFILES:
        raise ValidationError(
            f"Unsupported compression profile {profile!r}.",
            field="profile",
            suggestions=list(_CODEC_PROFILES),
        )
    return normalized


def validate_on_error(on_error: str | None) -> str | None:
    """Return a normalized parse-error policy or None.

    Raises:
        ValidationError: If on_error is set but not raise/skip/warn.
    """
    from .errors import ValidationError

    if not on_error:
        return None
    normalized = str(on_error).strip().lower()
    if normalized not in _ON_ERROR_POLICIES:
        raise ValidationError(
            f"Unsupported on-error policy {on_error!r}.",
            field="on_error",
            suggestions=list(_ON_ERROR_POLICIES),
        )
    return normalized


def validate_write_mode(write_mode: str | None) -> str | None:
    """Return a normalized lakehouse write mode or None.

    Raises:
        ValidationError: If write_mode is set but not a known mode.
    """
    from .errors import ValidationError

    if not write_mode:
        return None
    normalized = str(write_mode).strip().lower()
    if normalized not in _WRITE_MODES:
        raise ValidationError(
            f"Unsupported write mode {write_mode!r}.",
            field="write_mode",
            suggestions=list(_WRITE_MODES),
        )
    return normalized


def iter_projected_rows(
    rows: Iterable[Any],
    flatten_nested: bool,
    *,
    keep_parents: bool = True,
    max_depth: int | None = None,
) -> Iterator[Any]:
    """Yield rows, optionally unfolding nested dicts onto dotted paths."""
    if not flatten_nested:
        yield from rows
        return
    from iterable.helpers.nested import project_row_nested

    kwargs: dict[str, Any] = {"keep_parents": keep_parents}
    if max_depth is not None:
        kwargs["max_depth"] = max_depth
    for item in rows:
        if isinstance(item, dict):
            yield project_row_nested(item, **kwargs)
        else:
            yield item


def nested_max_depth(options: dict | None) -> int | None:
    """Return ``max_nested_depth`` from command options when set."""
    if not options:
        return None
    value = options.get("max_nested_depth")
    if value is None or value == "":
        return None
    return int(value)


def nested_keep_parents(options: dict | None, default: bool) -> bool:
    """Return ``keep_nested_parents`` from command options, or ``default``."""
    if not options or "keep_nested_parents" not in options:
        return default
    value = options.get("keep_nested_parents")
    if value is None:
        return default
    return bool(value)


def iter_command_rows(
    rows: Iterable[Any],
    options: dict | None,
    *,
    keep_parents_default: bool = True,
) -> Iterator[Any]:
    """Yield rows, unfolding nested dicts when ``flatten_nested`` is set."""
    flatten_nested = bool(options.get("flatten_nested")) if options else False
    return iter_projected_rows(
        rows,
        flatten_nested,
        keep_parents=nested_keep_parents(options, keep_parents_default),
        max_depth=nested_max_depth(options),
    )


def run_with_duckdb_fallback(
    operation: str,
    duckdb_fn: Callable[[], T],
    iterable_fn: Callable[[], T],
    engine: str | None = "duckdb",
) -> T:
    """Run a DuckDB implementation, falling back to the iterable engine on failure.

    Args:
        operation: Operation name used in the fallback log message (e.g. "count").
        duckdb_fn: Zero-argument callable implementing the DuckDB path.
        iterable_fn: Zero-argument callable implementing the iterable path.
        engine: Detected engine; the DuckDB path is only attempted when "duckdb".

    Returns:
        The result of whichever implementation ran.
    """
    if engine == "duckdb":
        try:
            return duckdb_fn()
        except Exception as e:  # noqa: BLE001 - any DuckDB failure falls back
            logger.warning(f"DuckDB {operation} failed, falling back to iterable: {e}")
    return iterable_fn()
