"""Fixlengths command: give every record the same fields."""

import logging

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import FixLengthsConfig, run
from ..ops.structure import FixLengths as FixLengthsOperation
from ..utils import get_option

logger = logging.getLogger(__name__)


class FixLengths:
    """Fixlengths command handler."""

    def fixlengths(self, fromfile, options=None):
        """Pad (or truncate) records to a common, alphabetically ordered field set.

        Args:
            fromfile: Input path.
            options: ``strategy`` (``pad`` or ``truncate``), ``value`` for missing fields,
                ``output`` and reader options.

        Raises:
            ValidationError: If the strategy is unknown.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        strategy = get_option(options, "strategy") or "pad"
        if strategy not in ("pad", "truncate"):
            raise ValidationError(
                f"Unknown strategy '{strategy}'", field="strategy", suggestions=["pad", "truncate"]
            )
        cfg = FixLengthsConfig(strategy=strategy, value=get_option(options, "value") or "")
        source = open_source(fromfile, options)
        count = run(
            "fixlengths",
            cfg,
            source,
            get_option(options, "output"),
            fieldnames=FixLengthsOperation().fieldnames(source, cfg),
        )
        logger.debug("fixlengths: wrote %d records", count)
