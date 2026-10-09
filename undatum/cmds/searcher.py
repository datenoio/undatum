"""Search command: keep records matching a regular expression."""

import logging
import re

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import SearchConfig, run_steps
from ..ops.expr import where_steps
from ..utils import get_option

logger = logging.getLogger(__name__)


class Searcher:
    """Search command handler."""

    def search(self, fromfile, options=None):
        """Keep the records where a field matches ``pattern``.

        Args:
            fromfile: Input path.
            options: ``pattern``, ``fields`` (comma-separated, default all),
                ``ignore_case``, ``output``, ``engine`` and reader options.

        Raises:
            ValidationError: If the pattern is missing or invalid.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        pattern = get_option(options, "pattern")
        if not pattern:
            raise ValidationError("search requires a pattern", field="pattern")
        ignore_case = bool(get_option(options, "ignore_case"))
        try:
            re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error as e:
            raise ValidationError(f"Invalid regex pattern: {e}", field="pattern") from e
        fields = get_option(options, "fields")
        cfg = SearchConfig(
            pattern=pattern,
            fields=tuple(f.strip() for f in fields.split(",")) if fields else None,
            ignore_case=ignore_case,
        )
        count = run_steps(
            [*where_steps(options), ("search", cfg)],
            open_source(fromfile, options),
            get_option(options, "output"),
            engine=get_option(options, "engine") or "auto",
        )
        logger.debug("search: wrote %d records", count)
