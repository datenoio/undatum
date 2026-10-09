"""Shared schema utility functions for schema extraction and analysis.

This module provides common functions used by both schema extraction
and data analysis commands to eliminate code duplication.
"""

from typing import Any

import duckdb
import pandas as pd

from .command_utils import duckdb_read_csv_expr

# DuckDB type → Frictionless Table Schema type (shared by packager and schemer).
DUCKDB_FRICTIONLESS_TYPE_MAP = {
    "VARCHAR": "string",
    "BIGINT": "integer",
    "INTEGER": "integer",
    "DOUBLE": "number",
    "FLOAT": "number",
    "BOOLEAN": "boolean",
    "DATE": "date",
    "TIMESTAMP": "datetime",
    "STRUCT": "object",
    "JSON": "object",
}

# DuckDB type → JSON Schema type string (schemer JSON Schema export).
DUCKDB_JSON_SCHEMA_TYPE_MAP = {
    "VARCHAR": "string",
    "BIGINT": "integer",
    "INTEGER": "integer",
    "DOUBLE": "number",
    "FLOAT": "number",
    "BOOLEAN": "boolean",
    "DATE": "string",
    "TIMESTAMP": "string",
    "STRUCT": "object",
    "JSON": "string",
}


def column_type_parse(column_type: str) -> list:
    """Parse column type string to extract array flag and base type.

    Args:
        column_type: DuckDB column type string (e.g., 'VARCHAR[]', 'STRUCT')

    Returns:
        List with [base_type, is_array_string] where is_array_string is 'True' or 'False'
    """
    is_array = column_type[-2:] == "[]"
    if is_array:
        text = column_type[:-2]
    else:
        text = column_type
    if text[:6] == "STRUCT":
        atype = text[:6]
    elif text[:4] == "JSON":
        atype = "VARCHAR"
    else:
        atype = text
    return [atype, str(is_array)]


def duckdb_to_frictionless_type(duckdb_type: str, is_array: bool) -> dict[str, Any]:
    """Convert DuckDB type to Frictionless Table Schema field type descriptor.

    Args:
        duckdb_type: DuckDB type string (e.g., 'VARCHAR', 'BIGINT').
        is_array: Whether the field is an array.

    Returns:
        Frictionless type dict or scalar type string wrapper.
    """
    base_type = DUCKDB_FRICTIONLESS_TYPE_MAP.get(duckdb_type, "string")
    if is_array:
        return {"type": "array", "items": {"type": base_type}}
    return {"type": base_type}


def duckdb_to_json_schema_type(duckdb_type: str, is_array: bool) -> str | dict[str, Any]:
    """Convert DuckDB type to JSON Schema type.

    Args:
        duckdb_type: DuckDB type string.
        is_array: Whether the field is an array.

    Returns:
        JSON Schema type string or dict.
    """
    json_type = DUCKDB_JSON_SCHEMA_TYPE_MAP.get(duckdb_type, "string")
    if is_array:
        return {"type": "array", "items": {"type": json_type}}
    return json_type


def field_to_frictionless_schema(field: Any) -> dict[str, Any]:
    """Convert an analyzer ``FieldSchema`` to a Frictionless Table Schema field.

    Args:
        field: Object with ``name``, ``ftype``, ``is_array``, optional stats and description.

    Returns:
        Frictionless Table Schema field dictionary.
    """
    field_schema: dict[str, Any] = {"name": field.name}
    field_schema.update(duckdb_to_frictionless_type(field.ftype, field.is_array))
    if getattr(field, "description", None):
        field_schema["description"] = field.description
    unique_count = getattr(field, "unique_count", None)
    total_count = getattr(field, "total_count", None)
    if unique_count is not None and total_count is not None and total_count > 0:
        if unique_count == total_count:
            field_schema["unique"] = True
    return field_schema


def duckdb_decompose(
    filename: str | None = None,
    frame: pd.DataFrame | None = None,
    filetype: str | None = None,
    path: str = "*",
    limit: int = 10000000,
    recursive: bool = True,
    root: str = "",
    ignore_errors: bool = True,
    use_summarize: bool = False,
    delimiter: str | None = None,
) -> list[Any]:
    """Decompose file or DataFrame structure using DuckDB.

    This function uses DuckDB's describe or summarize functions to extract
    schema information from nested data structures. It handles up to 4 levels
    of nesting by constructing recursive SQL queries.

    Args:
        filename: Path to input file. If None, frame must be provided.
        frame: Pandas DataFrame. Used when filename is None.
        filetype: File type ('csv', 'tsv', 'json', 'jsonl'). Determines read function.
        path: Path expression for nested fields (default: '*' for all fields).
        limit: Maximum records to process (default: 10000000).
        recursive: Whether to recursively process STRUCT types (default: True).
        root: Root path prefix for nested queries (used internally for recursion).
        ignore_errors: Whether to ignore parsing errors in DuckDB (default: True).
        use_summarize: If True, use 'summarize' (for analyzer), else use 'describe' (for schemer).
        delimiter: CSV/TSV delimiter (passed to DuckDB read_csv when set).

    Returns:
        List of lists containing field information:
        - If use_summarize=True: [field_path, base_type, is_array, unique_count, total_count, uniqueness_percentage]
        - If use_summarize=False: [field_path, base_type, is_array]

    Raises:
        ValueError: If both filename and frame are None.
        duckdb.Error: If DuckDB query fails.
    """
    if filename is None and frame is None:
        raise ValueError("Either filename or frame must be provided")

    json_ignore = ", ignore_errors=true" if ignore_errors else ""
    data: list = []
    if filetype in ["csv", "tsv"]:
        if filename is not None:
            # For schemer (describe), use sample_size; for analyzer (summarize), don't
            if use_summarize:
                read_func = duckdb_read_csv_expr(filename, delimiter, ignore_errors=ignore_errors)
            else:
                read_func = duckdb_read_csv_expr(
                    filename,
                    delimiter,
                    ignore_errors=ignore_errors,
                    sample_size=limit,
                )
        else:
            read_func = "frame"
    elif filetype in ["json", "jsonl"]:
        if filename is not None:
            read_func = f"read_json('{filename}'{json_ignore})"
        else:
            read_func = "frame"
    elif filename is not None:
        read_func = f"'{filename}'"
    else:
        read_func = "frame"

    # Choose query command based on use_summarize flag
    query_cmd = "summarize" if use_summarize else "describe"

    if path == "*":
        if filename is not None or frame is not None:
            if frame is not None:
                # Only include limit if it's not None
                limit_clause = f" limit {limit}" if limit is not None else ""
                query_str = f"{query_cmd} select {path} from {read_func}{limit_clause}"
            else:
                # Only include limit if it's not None
                limit_clause = f" limit {limit}" if limit is not None else ""
                query_str = f"{query_cmd} select {path} from {read_func}{limit_clause}"
            # Execute query with error handling for None column references
            try:
                data = duckdb.sql(query_str).fetchall()
            except (duckdb.Error, Exception) as e:
                error_msg = str(e)
                # Only catch specific "Referenced column 'None' not found" errors
                if (
                    "Referenced column" in error_msg
                    and '"None"' in error_msg
                    and "not found" in error_msg
                ):
                    # None column reference error - return empty result to prevent error propagation
                    if ignore_errors:
                        return []
                    # If not ignoring errors, this will raise
                # Re-raise if ignore_errors is False, otherwise return empty result for other errors
                if not ignore_errors:
                    raise
                return []
    else:
        # Validate path before using it in SQL queries
        if not path or not isinstance(path, str) or path in {"None", ""}:
            # Return empty result if path is invalid
            return []

        path_parts = path.split(".")
        # Validate that no path parts are None or "None"
        if any(not part or part == "None" or not isinstance(part, str) for part in path_parts):
            # Return empty result if any path part is invalid
            return []

        query = None
        # Build limit clause only if limit is not None
        limit_clause = f" limit {limit}" if limit is not None else ""

        if len(path_parts) == 1:
            if filename is not None:
                query = (
                    f'{query_cmd} select unnest("{path}", recursive:=true) '
                    f"from {read_func}{limit_clause}"
                )
            else:
                query = (
                    f'{query_cmd} select unnest("{path}", recursive:=true) '
                    f"from {read_func}{limit_clause}"
                )
        elif len(path_parts) == 2:
            if filename is not None:
                query = (
                    f'{query_cmd} select unnest("{path_parts[1]}", '
                    f'recursive:=true) from (select unnest("{path_parts[0]}", '
                    f"recursive:=true) from {read_func}{limit_clause})"
                )
            else:
                query = (
                    f'{query_cmd} select unnest("{path_parts[1]}", '
                    f'recursive:=true) from (select unnest("{path_parts[0]}", '
                    f"recursive:=true) from {read_func}{limit_clause})"
                )
        elif len(path_parts) == 3:
            if filename is not None:
                query = (
                    f'{query_cmd} select unnest("{path_parts[2]}", '
                    f'recursive:=true) from (select unnest("{path_parts[1]}", '
                    f'recursive:=true) from (select unnest("{path_parts[0]}", '
                    f"recursive:=true) from {read_func}{limit_clause}))"
                )
            else:
                query = (
                    f'{query_cmd} select unnest("{path_parts[2]}", '
                    f'recursive:=true) from (select unnest("{path_parts[1]}", '
                    f'recursive:=true) from (select unnest("{path_parts[0]}", '
                    f"recursive:=true) from {read_func}{limit_clause}))"
                )
        elif len(path_parts) == 4:
            if filename is not None:
                query = (
                    f'{query_cmd} select unnest("{path_parts[2]}.{path_parts[3]}", '
                    f'recursive:=true) from (select unnest("{path_parts[1]}", '
                    f'recursive:=true) from (select unnest("{path_parts[0]}", '
                    f"recursive:=true) from {read_func}{limit_clause}))"
                )
            else:
                query = (
                    f'{query_cmd} select unnest("{path_parts[2]}.{path_parts[3]}", '
                    f'recursive:=true) from (select unnest("{path_parts[1]}", '
                    f'recursive:=true) from (select unnest("{path_parts[0]}", '
                    f"recursive:=true) from {read_func}{limit_clause}))"
                )
        if query is None:
            # Nesting deeper than four levels is not decomposed with DuckDB.
            return []
        # Execute query with error handling for None column references
        try:
            data = duckdb.sql(query).fetchall()
        except (duckdb.Error, Exception) as e:
            # If query fails due to None column reference, return empty result
            error_msg = str(e)
            # Only catch specific "Referenced column 'None' not found" errors
            if (
                "Referenced column" in error_msg
                and '"None"' in error_msg
                and "not found" in error_msg
            ):
                # This is a None column reference issue - return empty to prevent error propagation
                if ignore_errors:
                    return []
                # If not ignoring errors, this will raise
            # Re-raise if ignore_errors is False, otherwise return empty result for other errors
            if not ignore_errors:
                raise
            return []

    table = []
    for row in data:
        # Skip rows where column name is None or invalid
        if not row or len(row) < 2:
            continue

        # Safely extract field_name with multiple checks
        field_name = row[0]

        # Skip if field_name is None (Python None object)
        if field_name is None:
            continue

        # Convert to string and check - handle case where None becomes "None"
        try:
            field_name_str = str(field_name) if field_name is not None else None
        except Exception:
            continue

        # Skip empty string, "None" string, or invalid field names
        if not field_name_str or field_name_str in {"None", ""}:
            continue

        # Additional check: ensure field_name_str doesn't contain "None" as a segment
        if (
            ".None." in field_name_str
            or field_name_str.startswith("None.")
            or field_name_str.endswith(".None")
        ):
            continue

        # Use the string version
        field_name = field_name_str

        # Build item path - ensure root is valid
        if len(root) == 0:
            item = [field_name]
        # Validate root before concatenation
        elif root and isinstance(root, str) and root != "None":
            item = [root + "." + field_name]
        else:
            item = [field_name]

        # Parse column type - validate row[1] exists and is a string
        if len(row) < 2 or row[1] is None:
            continue

        # Ensure row[1] is a string for column_type_parse
        try:
            column_type_str = str(row[1]) if row[1] is not None else None
            if not column_type_str:
                continue
        except Exception:
            continue

        parsed_type = column_type_parse(column_type_str)
        if not parsed_type or len(parsed_type) < 2:
            continue

        item.extend(parsed_type)

        # If using summarize, add additional statistics
        if use_summarize:
            try:
                # DuckDB summarize returns: [column_name, column_type, ..., unique_count, ..., total_count, ...]
                # Indices may vary, try to find them - typically unique_count is around index 4-5, total_count around 10-11
                unique_count = "0"
                total_count = "0"
                uniq_share = 0.0

                # Try to extract unique_count and total_count - be flexible with indices
                if len(row) > 4:
                    # Try common positions for unique_count
                    for idx in [4, 5, 6]:
                        if idx < len(row) and row[idx] is not None:
                            try:
                                unique_count = str(int(row[idx]))
                                break
                            except (ValueError, TypeError):
                                continue

                if len(row) > 10:
                    # Try common positions for total_count
                    for idx in [10, 11, 12]:
                        if idx < len(row) and row[idx] is not None:
                            try:
                                total_count = str(int(row[idx]))
                                # Calculate uniqueness percentage
                                total_val = float(row[idx])
                                unique_val = float(unique_count)
                                if total_val > 0:
                                    uniq_share = (unique_val * 100.0) / total_val
                                break
                            except (ValueError, TypeError, ZeroDivisionError):
                                continue

                # Always append the statistics fields (even if 0) to maintain expected format
                item.append(unique_count)
                item.append(total_count)
                item.append(f"{uniq_share:0.2f}")  # uniqueness_percentage
            except (IndexError, ValueError, TypeError):
                # If statistics extraction completely fails, use defaults to maintain format
                item.append("0")  # unique_count
                item.append("0")  # total_count
                item.append("0.00")  # uniqueness_percentage

        table.append(item)

        if recursive and parsed_type[0] == "STRUCT":
            # Build sub_path safely
            if len(root) == 0:
                sub_path = field_name
            else:
                sub_path = item[0] if item and len(item) > 0 else field_name

            # Validate sub_path thoroughly before recursive call
            if (
                sub_path
                and isinstance(sub_path, str)
                and sub_path not in {"None", ""}
                and ".None." not in sub_path
                and not sub_path.startswith("None.")
                and not sub_path.endswith(".None")
            ):
                try:
                    subtable = duckdb_decompose(
                        filename,
                        frame,
                        filetype=filetype,
                        path=sub_path,
                        limit=limit,
                        recursive=recursive,
                        root=item[0] if item and len(item) > 0 else sub_path,
                        ignore_errors=ignore_errors,
                        use_summarize=use_summarize,
                        delimiter=delimiter,
                    )
                    for subitem in subtable:
                        table.append(subitem)
                except Exception:
                    # If recursive call fails, continue processing other fields
                    if ignore_errors:
                        continue
                    raise

    return table
