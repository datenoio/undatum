"""Engine detection for statistics processing."""

from ...common.engine_selector import detect_engine

# Names stats reports for the normalized types of undatum.common.field_types; other types
# (strings, objects, arrays, times, binary values, no values) are "str".
STATS_TYPE_NAMES = {
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "date": "date",
    "datetime": "datetime",
}


def stats_type_names(types, codes=()):
    """Stats type names for normalized ``types``; ``codes`` (digits with leading zeros) are numstr."""
    return {
        field: "numstr" if field in codes else STATS_TYPE_NAMES.get(kind, "str")
        for field, kind in types.items()
    }


def _detect_engine(fromfile, engine, filetype):
    """Detect the appropriate engine for statistics processing.

    Args:
        fromfile: Path to input file
        engine: Engine preference ('auto', 'duckdb', 'python'; 'iterable' is an alias)
        filetype: Optional file type override (if None, will be detected)

    Returns:
        Detected engine name: 'duckdb' or 'iterable'
    """
    return detect_engine(fromfile, engine, filetype, operation="stats")
