"""Fill command: fill empty values with a constant or a neighbour value."""

import logging

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import FillConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)

STRATEGIES = ("constant", "forward", "backward")


class Filler:
    """Fill command handler."""

    def fill(self, fromfile, options=None):
        """Fill empty (missing, null or empty string) values.

        Args:
            fromfile: Input path.
            options: ``fields`` (comma-separated, default all), ``strategy``
                (``constant``, ``forward``, ``backward``), ``value``, ``output``, ``engine``
                and reader options.

        Raises:
            ValidationError: If the strategy is unknown.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        strategy = get_option(options, "strategy") or "constant"
        if strategy not in STRATEGIES:
            raise ValidationError(
                f"Unknown fill strategy '{strategy}'",
                field="strategy",
                suggestions=list(STRATEGIES),
            )
        fields = get_option(options, "fields")
        cfg = FillConfig(
            fields=tuple(f.strip() for f in fields.split(",")) if fields else None,
            strategy=strategy,
            value=get_option(options, "value") or "",
        )
        count = run(
            "fill",
            cfg,
            open_source(fromfile, options),
            get_option(options, "output"),
            engine=get_option(options, "engine") or "auto",
        )
        logger.debug("fill: wrote %d records", count)
