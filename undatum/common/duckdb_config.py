"""DuckDB connection configuration and factory."""

import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Literal

import duckdb

logger = logging.getLogger(__name__)

# Defaults per kind of work; explicit --duckdb-* options always win.
# - row: row-wise and window transforms are I/O bound; one thread is nearly as fast and, with
#   insertion order preserved, per-thread buffers would otherwise grow with the input.
# - ordered: queries that hold every record and rely on input order (row_number() over the
#   input); one thread, and DuckDB's own memory limit since a small one fails their sorts.
# - aggregate: aggregations, sorts and profiling use every core and DuckDB's memory limit.
Workload = Literal["row", "ordered", "aggregate"]
WORKLOAD_DEFAULTS: dict[str, dict[str, Any]] = {
    "row": {"threads": 1, "memory": "256MB"},
    "ordered": {"threads": 1},
    "aggregate": {},
}

# Directory with preinstalled DuckDB extensions (DuckDB's extension_directory), so commands
# that need an extension work without network access.
EXTENSION_DIR_ENV = "UNDATUM_DUCKDB_EXTENSION_DIR"


def parse_memory_size(memory_str: str) -> int:
    """Parse memory size string to bytes.

    Args:
        memory_str: Memory size string (e.g., '4GB', '512MB', '1024')

    Returns:
        Memory size in bytes

    Examples:
        >>> parse_memory_size('4GB')
        4294967296
        >>> parse_memory_size('512MB')
        536870912
        >>> parse_memory_size('1024')
        1024
    """
    if not memory_str:
        return 0

    # Remove whitespace and convert to lowercase
    memory_str = memory_str.strip().lower()

    # Match pattern: number followed by optional unit (GB, MB, KB, or bytes)
    match = re.match(r"^(\d+)(gb|mb|kb|b)?$", memory_str)
    if not match:
        raise ValueError(f"Invalid memory size format: {memory_str}")

    size = int(match.group(1))
    unit = match.group(2) or "b"

    multipliers = {"gb": 1024**3, "mb": 1024**2, "kb": 1024, "b": 1}
    return size * multipliers[unit]


def create_duckdb_connection(
    threads: int | None = None,
    memory: str | None = None,
    temp_dir: str | None = None,
    database: str | None = None,
) -> duckdb.DuckDBPyConnection:
    """Create a configured DuckDB connection.

    Args:
        threads: Number of threads (optional)
        memory: Memory limit as string (e.g., '4GB', '512MB') (optional)
        temp_dir: Temporary directory path (optional)
        database: Database path (default: ':memory:') (optional)

    Returns:
        Configured DuckDB connection
    """
    if database is None:
        database = ":memory:"

    conn = duckdb.connect(database=database)

    extension_dir = os.environ.get(EXTENSION_DIR_ENV)
    if extension_dir:
        escaped = extension_dir.replace("'", "''")
        conn.execute(f"SET extension_directory='{escaped}'")

    # Configure threads
    if threads is not None:
        if threads < 1:
            raise ValueError(f"Thread count must be >= 1, got {threads}")
        conn.execute(f"SET threads={threads}")
        logger.debug(f"DuckDB threads set to {threads}")

    # Configure memory limit
    if memory:
        try:
            memory_bytes = parse_memory_size(memory)
            if memory_bytes > 0:
                # DuckDB requires a unit suffix; bare integers raise:
                # "Unknown unit for memory: ''"
                conn.execute(f"SET memory_limit='{memory_bytes}B'")
                logger.debug(f"DuckDB memory limit set to {memory_bytes} bytes ({memory})")
        except ValueError as e:
            logger.warning(f"Invalid memory size format: {memory}, error: {e}")

    # Configure temp directory
    if temp_dir:
        if not os.path.exists(temp_dir):
            try:
                os.makedirs(temp_dir, exist_ok=True)
            except OSError as e:
                logger.warning(f"Could not create temp directory {temp_dir}: {e}")
        if os.path.exists(temp_dir) and os.path.isdir(temp_dir):
            # DuckDB uses temp_directory setting
            conn.execute(f"SET temp_directory='{temp_dir}'")
            logger.debug(f"DuckDB temp directory set to {temp_dir}")
        else:
            logger.warning(f"Temp directory does not exist or is not a directory: {temp_dir}")

    return conn


@contextmanager
def one_thread(conn: Any) -> Iterator[Any]:
    """Run the queries of the block on one thread of ``conn``, then restore its setting.

    For samples (``LIMIT``): parallel CSV readers buffer far beyond the rows a sample needs
    (about 115 MB more on 1M rows with 14 threads).
    """
    threads = conn.execute("SELECT current_setting('threads')").fetchall()[0][0]
    conn.execute("SET threads = 1")
    try:
        yield conn
    finally:
        conn.execute(f"SET threads = {int(threads)}")


def load_extension(conn: duckdb.DuckDBPyConnection, name: str) -> None:
    """Load the DuckDB extension ``name``, downloading it first when it is not installed.

    Args:
        conn: Connection made by :func:`create_duckdb_connection`.
        name: Extension name, such as ``excel``.

    Raises:
        ConfigurationError: The extension is not installed and cannot be downloaded (exit
            code 2); the message says how to install it for offline use.
    """
    try:
        conn.load_extension(name)
        return
    except duckdb.Error:
        pass
    try:
        conn.install_extension(name)
        conn.load_extension(name)
    except duckdb.Error as exc:
        from .errors import ConfigurationError

        raise ConfigurationError(
            f"DuckDB extension '{name}' is not installed and could not be downloaded: {exc}",
            config_key=EXTENSION_DIR_ENV,
            fix_hint=(
                f"On a machine with network access run `undatum extensions install {name} "
                f"--dir DIR`, copy DIR to this machine and set {EXTENSION_DIR_ENV} to it."
            ),
        ) from exc


def get_duckdb_config_from_options(options: dict) -> dict:
    """Extract DuckDB configuration from options dictionary.

    Args:
        options: Options dictionary

    Returns:
        Dictionary with DuckDB configuration (threads, memory, temp_dir)
    """
    from ..utils import get_option

    config = {}
    duckdb_threads = get_option(options, "duckdb_threads")
    threads = get_option(options, "threads")
    if duckdb_threads is not None:
        config["threads"] = duckdb_threads
    elif threads is not None:
        # Fall back to the generic --threads option when no DuckDB-specific value is given
        config["threads"] = threads
    if "duckdb_memory" in options:
        config["memory"] = options["duckdb_memory"]
    if "duckdb_temp_dir" in options:
        config["temp_dir"] = options["duckdb_temp_dir"]
    return config


def duckdb_connection(
    options: dict[str, Any] | None = None, workload: Workload = "aggregate"
) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection for one command, configured from its ``--duckdb-*`` options.

    Args:
        options: Command options (``duckdb_threads``, ``duckdb_memory``, ``duckdb_temp_dir``;
            ``threads`` when ``duckdb_threads`` is not given).
        workload: ``row``, ``ordered`` or ``aggregate`` (see ``WORKLOAD_DEFAULTS``); fills the
            settings the options leave unset.

    Returns:
        A new connection; the caller closes it.
    """
    config = get_duckdb_config_from_options(options or {})
    for key, value in WORKLOAD_DEFAULTS[workload].items():
        if not config.get(key):
            config[key] = value
    return create_duckdb_connection(**config)
