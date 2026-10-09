"""Sort command module - sort rows by columns."""

import logging
import uuid

from ..common.command_utils import (
    ITERABLE_OPTIONS_KEYS,  # noqa: F401
    force_iterable_if_table,
    get_iterable_options,
    iter_command_rows,
)
from ..common.duckdb_config import create_duckdb_connection, get_duckdb_config_from_options
from ..common.engine_selector import detect_engine
from ..common.errors import (
    FileNotFoundError,
    PermissionError,
    ValidationError,
    find_similar_files,
)
from ..common.external_sort import DEFAULT_RUN_SIZE, external_merge_sort
from ..common.path_utils import validate_file_path
from ..common.s3_iterable import open_path as open_iterable
from ..common.writer import emit_records
from ..io import RowSource
from ..ops import write_query
from ..ops.base import quote
from ..utils import get_option

logger = logging.getLogger(__name__)

# Threshold for using external sort (in-memory vs external merge)
EXTERNAL_SORT_THRESHOLD = 100000  # items


def _normalize_for_json(obj):
    """Convert non-JSON-serializable types to JSON-serializable ones.

    Recursively converts UUID objects and other non-serializable types to strings.

    Args:
        obj: Object to normalize (can be dict, list, or primitive type)

    Returns:
        Normalized object with non-serializable types converted to strings
    """
    if isinstance(obj, uuid.UUID):
        return str(obj)
    elif isinstance(obj, dict):
        return {key: _normalize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_normalize_for_json(item) for item in obj]
    else:
        return obj


def _get_sort_key(item, sort_fields, numeric_fields=None):
    """Get sort key for an item."""
    if not isinstance(item, dict):
        return item

    numeric_set = set(numeric_fields or [])
    keys = []
    for field in sort_fields:
        value = item.get(field)
        if field in numeric_set:
            # Try to convert to number for numeric sort
            try:
                keys.append(float(value) if value is not None else float("-inf"))
            except (ValueError, TypeError):
                keys.append(value)
        else:
            keys.append(value)
    return tuple(keys)


class Sorter:
    """Sorter command handler - sort rows."""

    def __init__(self):
        pass

    def sort(self, fromfile, options=None):
        """Sort rows by one or more columns."""
        if options is None:
            options = {}

        # Validate input file exists and is readable
        try:
            validate_file_path(fromfile, check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(fromfile)
            raise FileNotFoundError(fromfile, suggestions) from e
        except PermissionError as e:
            raise PermissionError(fromfile, operation="read") from e

        logger.debug("Processing %s", fromfile)
        iterableargs = get_iterable_options(options)
        filetype = get_option(options, "filetype")
        engine = get_option(options, "engine") or "auto"
        by_fields = get_option(options, "by")
        descending = get_option(options, "desc") or False
        numeric_fields = get_option(options, "numeric")
        to_file = get_option(options, "output")

        if not by_fields:
            raise ValidationError("Sort fields (--by) are required", field="by")

        # Parse sort fields
        sort_fields = [f.strip() for f in by_fields.split(",")]
        numeric_set = {f.strip() for f in numeric_fields.split(",")} if numeric_fields else set()

        detected_engine = detect_engine(fromfile, engine, filetype, operation="sort")
        detected_engine = force_iterable_if_table(options, detected_engine)

        # Initialize items for output handling
        items = []

        if detected_engine == "duckdb":
            try:
                # Get DuckDB configuration from options
                duckdb_config = get_duckdb_config_from_options(options)
                conn = create_duckdb_connection(**duckdb_config)

                # The shared reader: escaped path, CSV dialect, doubled quotes, codecs.
                read_expr = RowSource(fromfile, options).duckdb_from()
                if read_expr is None:
                    raise ValueError("DuckDB cannot read this input")

                # Build ORDER BY clause
                direction = "DESC" if descending else "ASC"
                order_by_parts = []
                for field in sort_fields:
                    if field in numeric_set:
                        # Cast to numeric for proper sorting
                        order_by_parts.append(f"CAST({quote(field)} AS DOUBLE) {direction}")
                    else:
                        order_by_parts.append(f"{quote(field)} {direction}")

                order_by = ", ".join(order_by_parts)
                query = f"SELECT * FROM {read_expr} ORDER BY {order_by}"

                # DuckDB sorts out of core; results are written in batches (COPY for files).
                try:
                    write_query(conn, query, to_file)
                finally:
                    conn.close()
                logger.info("sort: completed using DuckDB")
                return
            except Exception as e:
                logger.warning(f"DuckDB sort failed, falling back to iterable: {e}")
                detected_engine = "iterable"

        if detected_engine == "iterable":
            reverse = descending

            def key_fn(x):
                return _get_sort_key(x, sort_fields, numeric_set)

            low_memory = bool(get_option(options, "low_memory"))
            run_size = int(get_option(options, "run_size") or DEFAULT_RUN_SIZE)
            temp_dir = get_option(options, "temp_dir") or get_option(options, "duckdb_temp_dir")

            iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
            try:
                records = iter_command_rows(iterable, options)
                if low_memory:
                    logger.info(
                        "sort: using external merge sort (--low-memory, run_size=%s)", run_size
                    )
                    sorted_iter = external_merge_sort(
                        records,
                        key_fn,
                        reverse=reverse,
                        run_size=run_size,
                        temp_dir=temp_dir,
                    )
                    _write_sorted_stream(sorted_iter, to_file)
                    return

                buffered = []
                for item in records:
                    buffered.append(item)
                    if len(buffered) > EXTERNAL_SORT_THRESHOLD:
                        logger.info(
                            "sort: exceeded %d records, using external merge sort",
                            EXTERNAL_SORT_THRESHOLD,
                        )

                        def _record_stream(first=buffered, rest=records):
                            yield from first
                            yield from rest

                        sorted_iter = external_merge_sort(
                            _record_stream(),
                            key_fn,
                            reverse=reverse,
                            run_size=run_size,
                            temp_dir=temp_dir,
                        )
                        _write_sorted_stream(sorted_iter, to_file)
                        return

                buffered.sort(key=key_fn, reverse=reverse)
                items = buffered
                logger.debug("sort: sorted %d records in memory", len(items))
            finally:
                iterable.close()

        emit_records(items, to_file)


def _write_sorted_stream(sorted_iter, to_file):
    """Stream sorted records to output without materializing the full list."""
    records = (_normalize_for_json(item) for item in sorted_iter)
    count = emit_records(records, to_file)
    logger.debug("sort: wrote %d records via external merge", count)
