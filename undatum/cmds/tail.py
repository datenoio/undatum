"""Tail command: the last N records."""

import logging

from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import TailConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)


class Tail:
    """Tail command handler."""

    def tail(self, fromfile, options=None):
        """Write the last ``n`` records (default 10); memory holds only those.

        Args:
            fromfile: Input path.
            options: ``n``, ``output`` and reader options.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        cfg = TailConfig(limit=int(get_option(options, "n") or 10))
        count = run("tail", cfg, open_source(fromfile, options), get_option(options, "output"))
        logger.debug("tail: wrote %d records", count)
