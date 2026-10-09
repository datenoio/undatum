"""Slice command: records by position."""

import logging

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import SliceConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)


class Slicer:
    """Slice command handler."""

    def slice(self, fromfile, options=None):
        """Write records by 0-based position: a range or a list of indices.

        Args:
            fromfile: Input path.
            options: ``start``, ``end`` (inclusive), ``indices`` (comma-separated),
                ``output``, ``engine`` and reader options.

        Raises:
            ValidationError: If neither a range nor indices are given.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        start = get_option(options, "start")
        end = get_option(options, "end")
        indices = get_option(options, "indices")
        if indices:
            try:
                wanted = frozenset(int(i.strip()) for i in str(indices).split(",") if i.strip())
            except ValueError as e:
                raise ValidationError(f"Invalid --indices: {e}", field="indices") from e
            cfg = SliceConfig(indices=wanted)
        elif start is not None or end is not None:
            cfg = SliceConfig(
                start=int(start) if start is not None else 0,
                end=int(end) + 1 if end is not None else None,  # --end is inclusive
            )
        else:
            raise ValidationError(
                "Either --start/--end or --indices must be specified", field="start"
            )
        count = run(
            "slice",
            cfg,
            open_source(fromfile, options),
            get_option(options, "output"),
            engine=get_option(options, "engine") or "auto",
        )
        logger.debug("slice: wrote %d records", count)
