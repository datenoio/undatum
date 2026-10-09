"""Engine selection utilities for choosing between DuckDB and Python engines."""

import logging
from typing import Any

from ..constants import DUCKABLE_CODECS, DUCKABLE_FILE_TYPES

logger = logging.getLogger(__name__)


def detect_file_type(path: str) -> Any:
    """iterabledata's format detection, imported on first use (the import takes ~1 s)."""
    from iterable.helpers.detect import detect_file_type as detect

    return detect(path)


# Accepted ``--engine`` values; ``iterable`` is the historical name of ``python``.
ENGINE_CHOICES = ("auto", "duckdb", "python")
ENGINE_ALIASES = {"iterable": "python"}


def validate_engine(engine: str | None) -> str:
    """Normalize an ``--engine`` value and reject unknown ones.

    Args:
        engine: Value from the CLI or config (``None`` means ``auto``).

    Returns:
        One of ``auto``, ``duckdb`` or ``python``.

    Raises:
        ValidationError: If the value is not a known engine.
    """
    if engine is None or engine == "":
        return "auto"
    value = str(engine).strip().lower()
    value = ENGINE_ALIASES.get(value, value)
    if value not in ENGINE_CHOICES:
        from .errors import ValidationError

        raise ValidationError(
            f"Unknown engine '{engine}'", field="engine", suggestions=list(ENGINE_CHOICES)
        )
    return value


def detect_engine(
    fromfile: str,
    engine: str | None = None,
    filetype: str | None = None,
    operation: str | None = None,
) -> str:
    """Detect the appropriate engine for processing.

    Args:
        fromfile: Path to input file
        engine: Requested engine ('auto', 'duckdb', 'python', or None for auto)
        filetype: File type if already known (optional)
        operation: Operation name for compatibility checking (optional)

    Returns:
        Selected engine: 'duckdb' or 'iterable' (Python engine)
    """
    engine = validate_engine(engine)

    compression = "raw"
    if filetype is None:
        ftype: Any = detect_file_type(fromfile)
        if ftype["success"]:
            filetype = ftype["datatype"].id()
            if ftype["codec"] is not None:
                compression = ftype["codec"].id()

    logger.debug("File filetype %s and compression %s", filetype, compression)

    if engine == "auto":
        if filetype in DUCKABLE_FILE_TYPES and compression in DUCKABLE_CODECS:
            # Check if operation is SQL-expressible (for future use)
            if operation and not _is_sql_expressible(operation):
                logger.debug("Operation %s not SQL-expressible, using iterable engine", operation)
                return "iterable"
            return "duckdb"
        return "iterable"

    if engine == "duckdb":
        return "duckdb"
    return "iterable"


def _is_sql_expressible(operation: str) -> bool:
    """Check if an operation can be expressed in SQL.

    Args:
        operation: Operation name (e.g., 'sort', 'filter', 'join')

    Returns:
        True if operation can be expressed in SQL, False otherwise
    """
    sql_expressible_operations = {
        "sort",
        "frequency",
        "uniq",
        "sample",
        "search",
        "dedup",
        "slice",
        "join",
        "select",
        "filter",
        "count",
        "stats",
    }
    return operation.lower() in sql_expressible_operations


def is_format_supported_by_duckdb(filetype: str | None, compression: str | None = None) -> bool:
    """Check if a file format is supported by DuckDB.

    Args:
        filetype: File type identifier
        compression: Compression codec identifier (optional)

    Returns:
        True if format is supported by DuckDB, False otherwise
    """
    if filetype not in DUCKABLE_FILE_TYPES:
        return False
    if compression is None:
        compression = "raw"
    return compression in DUCKABLE_CODECS
