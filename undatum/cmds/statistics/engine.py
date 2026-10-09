"""Engine detection for statistics processing."""

from ...common.engine_selector import detect_engine


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
