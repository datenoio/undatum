"""Transpose command: fields become records."""

import logging

from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import TransposeConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)


class Transposer:
    """Transpose command handler."""

    def transpose(self, fromfile, options=None):
        """Write one record per input field: ``field`` plus ``row_0``, ``row_1``, ...

        Args:
            fromfile: Input path.
            options: ``output`` and reader options.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        count = run(
            "transpose",
            TransposeConfig(),
            open_source(fromfile, options),
            get_option(options, "output"),
        )
        logger.debug("transpose: wrote %d records", count)
