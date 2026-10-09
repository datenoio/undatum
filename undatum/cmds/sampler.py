"""Sample command module - random sampling."""

import logging
import random

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
from ..common.path_utils import validate_file_path
from ..common.s3_iterable import open_path as open_iterable
from ..common.writer import emit_records
from ..ops import write_query
from ..utils import get_file_type, get_option, normalize_for_json  # noqa: F401

logger = logging.getLogger(__name__)


class Sampler:
    """Sampler command handler - random sampling."""

    def __init__(self):
        pass

    def sample(self, fromfile, options=None):
        """Randomly select rows using reservoir sampling algorithm."""
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
        filetype = get_option(options, "filetype") or get_option(options, "format_in")
        engine = get_option(options, "engine") or "auto"
        n = get_option(options, "n")
        percent = get_option(options, "percent")
        to_file = get_option(options, "output")

        # Determine sample size
        sample_size = None
        if n:
            sample_size = int(n)
        elif percent:
            # For DuckDB, we can calculate percentage in SQL
            # For iterable, need to count first
            sample_size = None  # Will be calculated based on engine
        else:
            raise ValidationError("Sample size (--n or --percent) is required", field="n")

        from ..ops.expr import where_steps

        steps = where_steps(options)
        if steps:
            from ..io import open_source
            from ..ops import SampleConfig, run_steps

            cfg = SampleConfig(size=sample_size, percent=float(percent) if percent else None)
            run_steps(
                [*steps, ("sample", cfg)],
                open_source(fromfile, options),
                to_file,
                engine=engine,
                format_out=get_option(options, "format_out"),
            )
            return

        detected_engine = detect_engine(fromfile, engine, filetype, operation="sample")
        detected_engine = force_iterable_if_table(options, detected_engine)
        items = []

        if detected_engine == "duckdb":
            try:
                duckdb_config = get_duckdb_config_from_options(options)
                conn = create_duckdb_connection(**duckdb_config)

                # Determine input format and build appropriate read expression
                source_type = filetype or get_file_type(fromfile) or "csv"
                if source_type == "csv":
                    read_expr = f"read_csv_auto('{fromfile}', all_varchar=true)"
                elif source_type in ("json", "jsonl"):
                    read_expr = f"read_json_auto('{fromfile}')"
                elif source_type == "parquet":
                    read_expr = f"read_parquet('{fromfile}')"
                else:
                    conn.close()
                    raise ValueError(f"Unsupported file type for DuckDB: {source_type}")

                # Build sampling query
                if n:
                    # Fixed number of samples
                    limit_value = int(n)
                    query = f"SELECT * FROM {read_expr} ORDER BY RANDOM() LIMIT {limit_value}"
                else:
                    # Percentage-based sampling
                    # First count total rows
                    count_query = f"SELECT COUNT(*) FROM {read_expr}"
                    total_count = conn.execute(count_query).fetchone()[0]
                    limit_value = max(1, int(total_count * float(percent) / 100))
                    query = f"SELECT * FROM {read_expr} ORDER BY RANDOM() LIMIT {limit_value}"

                try:
                    write_query(conn, query, to_file)
                finally:
                    conn.close()
                logger.info("sample: completed using DuckDB")
                return
            except Exception as e:
                logger.warning(f"DuckDB sample failed, falling back to iterable: {e}")
                detected_engine = "iterable"

        if detected_engine == "iterable":
            # Determine sample size for iterable engine
            if sample_size is None and percent:
                # Need to count first to calculate percentage
                count = 0
                iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
                try:
                    for _ in iterable:
                        count += 1
                finally:
                    iterable.close()
                sample_size = max(1, int(count * float(percent) / 100))

            if sample_size is None or sample_size <= 0:
                raise ValidationError(
                    "Sample size must be positive (--n or --percent)", field="percent"
                )

            # Reservoir sampling
            iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
            reservoir = []
            count = 0

            try:
                for item in iter_command_rows(iterable, options):
                    count += 1
                    if len(reservoir) < sample_size:
                        # Fill reservoir
                        reservoir.append(item)
                    else:
                        # Replace elements with gradually decreasing probability
                        j = random.randint(0, count - 1)
                        if j < sample_size:
                            reservoir[j] = item

                    if count % 100000 == 0:
                        logger.debug("sample: processed %d records", count)
            finally:
                iterable.close()

            items = reservoir
            logger.debug("sample: processed %d records, sampled %d", count, len(items))

        emit_records(items, to_file)
