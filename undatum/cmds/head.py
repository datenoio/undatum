"""Head command: the first N records."""

import logging

from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import HeadConfig, run_steps
from ..ops.expr import where_steps
from ..utils import get_option

logger = logging.getLogger(__name__)


class Head:
    """Head command handler."""

    def head(self, fromfile, options=None):
        """Write the first ``n`` records (default 10); reading stops after them.

        Args:
            fromfile: Input path.
            options: ``n``, ``output``, ``engine`` and reader options.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        cfg = HeadConfig(limit=int(get_option(options, "n") or 10))
        count = run_steps(
            [*where_steps(options), ("head", cfg)],
            open_source(fromfile, options),
            get_option(options, "output"),
            engine=get_option(options, "engine") or "auto",
        )
        logger.debug("head: wrote %d records", count)
