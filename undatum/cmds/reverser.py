"""Reverse command: records in reverse order."""

import logging

from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import ReverseConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)


class Reverser:
    """Reverse command handler."""

    def reverse(self, fromfile, options=None):
        """Write the records last-first; large inputs are buffered on disk, not in memory.

        Args:
            fromfile: Input path.
            options: ``output`` and reader options.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        count = run(
            "reverse",
            ReverseConfig(),
            open_source(fromfile, options),
            get_option(options, "output"),
        )
        logger.debug("reverse: wrote %d records", count)
