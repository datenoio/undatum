"""Dedup command: drop duplicate records."""

import logging

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import DedupConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)

# Unique keys indexed in memory before the index moves to disk.
DISK_DEDUP_THRESHOLD = 100_000


class Deduplicator:
    """Dedup command handler."""

    def dedup(self, fromfile, options=None):
        """Write each record whose key was not seen before (or the last one per key).

        Args:
            fromfile: Input path.
            options: ``key_fields`` (comma-separated; all fields when omitted), ``keep``
                (``first`` or ``last``), ``low_memory``, ``temp_dir``, ``output`` and reader
                options.

        Raises:
            ValidationError: If ``keep`` is not ``first`` or ``last``.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        keep = get_option(options, "keep") or "first"
        if keep not in ("first", "last"):
            raise ValidationError(
                f"Invalid keep value '{keep}'", field="keep", suggestions=["first", "last"]
            )
        key_fields = get_option(options, "key_fields")
        cfg = DedupConfig(
            keys=tuple(f.strip() for f in key_fields.split(",")) if key_fields else (),
            keep=keep,
            memory_keys=DISK_DEDUP_THRESHOLD,
            low_memory=bool(get_option(options, "low_memory")),
            temp_dir=get_option(options, "temp_dir") or get_option(options, "duckdb_temp_dir"),
        )
        count = run("dedup", cfg, open_source(fromfile, options), get_option(options, "output"))
        logger.debug("dedup: wrote %d records", count)
