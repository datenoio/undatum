"""Exclude command: drop records whose key appears in another file."""

import logging

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source, side_options
from ..ops import ExcludeConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)


class Excluder:
    """Exclude command handler."""

    def exclude(self, fromfile, exclude_file, options=None):
        """Write the records of ``fromfile`` whose ``on`` key is not in ``exclude_file``.

        Args:
            fromfile: Input path.
            exclude_file: Records whose keys are excluded (read with ``table2``/``sheet2``).
            options: ``on`` (comma-separated key fields, dotted paths allowed),
                ``output`` and reader options.

        Raises:
            ValidationError: If no key fields are given.
        """
        options = options or {}
        on_fields = get_option(options, "on")
        if not on_fields:
            raise ValidationError("exclude requires key fields (--on)", field="on")
        validate_file_path(fromfile, check_read=True)
        validate_file_path(exclude_file, check_read=True)
        cfg = ExcludeConfig(
            exclude=open_source(exclude_file, side_options(options, 2)),
            on=tuple(f.strip() for f in on_fields.split(",")),
        )
        count = run(
            "exclude",
            cfg,
            open_source(fromfile, side_options(options, 1)),
            get_option(options, "output"),
        )
        logger.debug("exclude: wrote %d records", count)
