"""Join command module - relational joins between two files."""

import logging

from ..common.command_utils import (
    ITERABLE_OPTIONS_KEYS,  # noqa: F401
    force_iterable_if_table,
    get_side_iterable_options,
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
from ..common.path_utils import validate_file_path
from ..common.progress import wrap_iterable
from ..common.s3_iterable import open_path as open_iterable
from ..ops import write_query, write_rows
from ..utils import field_values, get_file_type, get_option

logger = logging.getLogger(__name__)


def _get_key_value(item, key_fields):
    """Get key value for joining."""
    if not key_fields:
        # Use first field if no key specified
        if isinstance(item, dict) and item:
            return list(item.values())[0]
        return None
    if isinstance(item, dict):
        values = []
        for field in key_fields:
            found = field_values(item, field)
            values.append(found[0] if found else None)
        if len(values) == 1:
            return values[0]
        return tuple(values)
    return None


def _join_fieldnames(file1, file2, key_fields, options):
    """CSV header of a join: left fields, new right fields, ``<field>_2`` for overlaps."""
    from ..io import open_source, side_options

    def first_fields(path, side):
        row = next(iter(open_source(path, side_options(options, side))), None)
        return list(row) if isinstance(row, dict) else []

    left, right = first_fields(file1, 1), first_fields(file2, 2)
    keys = set(key_fields or [])
    return (
        left
        + [f for f in right if f not in left]
        + [f"{f}_2" for f in right if f in left and f not in keys]
    )


class Joiner:
    """Joiner command handler - relational joins."""

    def __init__(self):
        pass

    def join(self, file1, file2, options=None):
        """Perform relational join between two files."""
        if options is None:
            options = {}

        # Validate both input files exist and are readable
        try:
            validate_file_path(file1, check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(file1)
            raise FileNotFoundError(file1, suggestions) from e
        except PermissionError as e:
            raise PermissionError(file1, operation="read") from e

        try:
            validate_file_path(file2, check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(file2)
            raise FileNotFoundError(file2, suggestions) from e
        except PermissionError as e:
            raise PermissionError(file2, operation="read") from e

        logger.debug("Joining %s and %s", file1, file2)

        on_fields = get_option(options, "on")
        join_type = get_option(options, "type") or "inner"
        filetype1 = get_option(options, "filetype1")
        get_option(options, "filetype2")
        engine = get_option(options, "engine") or "auto"

        if not on_fields:
            raise ValidationError("Join key fields (--on) are required", field="on")

        key_field_list = [f.strip() for f in on_fields.split(",")]
        filetype2 = get_option(options, "filetype2")

        # Check if both files support DuckDB
        detected_engine1 = detect_engine(file1, engine, filetype1, operation="join")
        detected_engine2 = detect_engine(file2, engine, filetype2, operation="join")
        detected_engine = (
            "duckdb"
            if (detected_engine1 == "duckdb" and detected_engine2 == "duckdb")
            else "iterable"
        )
        detected_engine = force_iterable_if_table(options, detected_engine)

        if detected_engine == "duckdb":
            try:
                duckdb_config = get_duckdb_config_from_options(options)
                conn = create_duckdb_connection(**duckdb_config)

                # Determine input formats and build appropriate read expressions
                source_type1 = filetype1 or get_file_type(file1) or "csv"
                source_type2 = filetype2 or get_file_type(file2) or "csv"

                def build_read_expr(filename, filetype):
                    if filetype == "csv":
                        return f"read_csv_auto('{filename}', all_varchar=true)"
                    elif filetype in ("json", "jsonl"):
                        return f"read_json_auto('{filename}')"
                    elif filetype == "parquet":
                        return f"read_parquet('{filename}')"
                    else:
                        raise ValueError(f"Unsupported file type for DuckDB: {filetype}")

                read_expr1 = build_read_expr(file1, source_type1)
                read_expr2 = build_read_expr(file2, source_type2)

                # Build ON clause for multiple keys
                on_conditions = []
                for key_field in key_field_list:
                    on_conditions.append(f"t1.{key_field} = t2.{key_field}")
                on_clause = " AND ".join(on_conditions)

                # Map join type
                join_type_sql = {
                    "inner": "INNER",
                    "left": "LEFT",
                    "right": "RIGHT",
                    "full": "FULL OUTER",
                    "outer": "FULL OUTER",
                }.get(join_type.lower(), "INNER")

                query = f"""
                    SELECT *
                    FROM ({read_expr1}) t1
                    {join_type_sql} JOIN ({read_expr2}) t2
                    ON {on_clause}
                """

                to_file = get_option(options, "output")
                try:
                    write_query(conn, query, to_file)
                finally:
                    conn.close()
                logger.info("join: completed using DuckDB")
                return
            except Exception as e:
                logger.warning(f"DuckDB join failed, falling back to iterable: {e}")
                detected_engine = "iterable"

        # Hash-based join implementation
        iterableargs1 = get_side_iterable_options(options, 1)
        iterableargs2 = get_side_iterable_options(options, 2)

        show_progress = get_option(options, "progress") or False

        # Build hash index from file2 (right side)
        iterable2 = open_iterable(file2, mode="r", iterableargs=iterableargs2)
        file2_index = {}

        try:
            count2 = 0
            for item in wrap_iterable(
                iter_command_rows(iterable2, options),
                desc="Indexing right side",
                unit="rows",
                show_progress=show_progress,
            ):
                count2 += 1
                if isinstance(item, dict):
                    key = _get_key_value(item, key_field_list)
                    if key is not None:
                        if key not in file2_index:
                            file2_index[key] = []
                        file2_index[key].append(item)
        finally:
            iterable2.close()

        logger.debug("join: indexed %d records from %s", len(file2_index), file2)

        # Process file1 and join; records go to the writer as they are produced.
        counts = {"left": 0}

        def joined():
            matched_keys = set()
            iterable1 = open_iterable(file1, mode="r", iterableargs=iterableargs1)
            try:
                for item1 in wrap_iterable(
                    iter_command_rows(iterable1, options),
                    desc="Joining",
                    unit="rows",
                    show_progress=show_progress,
                ):
                    counts["left"] += 1
                    if not isinstance(item1, dict):
                        continue
                    key = _get_key_value(item1, key_field_list)
                    if key in file2_index:
                        matched_keys.add(key)
                        for item2 in file2_index[key]:
                            # Merge items; a differing value from file2 goes to "<field>_2".
                            joined_item = item1.copy()
                            for field, value in item2.items():
                                if field in item1 and item1[field] != value:
                                    joined_item[f"{field}_2"] = value
                                elif field not in item1:
                                    joined_item[field] = value
                            yield joined_item
                    elif join_type in ("left", "full", "outer"):
                        yield item1
            finally:
                iterable1.close()
            # Right and full outer joins add the unmatched records of file2.
            if join_type in ("right", "full", "outer"):
                for key, items2 in file2_index.items():
                    if key not in matched_keys:
                        yield from items2

        to_file = get_option(options, "output")
        count = write_rows(
            joined(),
            to_file,
            fieldnames=_join_fieldnames(file1, file2, key_field_list, options),
        )
        logger.debug(
            "join: %s join completed, %d rows from file1, %d indexed from file2, %d joined rows",
            join_type,
            counts["left"],
            len(file2_index),
            count,
        )
