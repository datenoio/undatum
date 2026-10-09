"""Rename command: rename fields by mapping or regular expression."""

import logging
import re

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import RenameConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)


def parse_mapping(text: str) -> dict[str, str]:
    """Parse ``old1:new1,old2:new2`` into a mapping."""
    mapping = {}
    for pair in text.split(","):
        if ":" in pair:
            old_name, new_name = pair.split(":", 1)
            mapping[old_name.strip()] = new_name.strip()
    return mapping


class Renamer:
    """Rename command handler."""

    def rename(self, fromfile, options=None):
        """Rename fields by exact mapping (``map``) or a regular expression (``pattern``).

        Args:
            fromfile: Input path.
            options: ``map`` (``old:new,...``), ``pattern``, ``replacement``, ``output``,
                ``engine`` and reader options.

        Raises:
            ValidationError: If neither a mapping nor a pattern is given, or the pattern
                is not a valid regular expression.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        mapping = get_option(options, "map")
        pattern = get_option(options, "pattern")
        if not mapping and not pattern:
            raise ValidationError("Either --map or --pattern option is required", field="map")
        if pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValidationError(f"Invalid regex pattern: {e}", field="pattern") from e
        cfg = RenameConfig(
            mapping=parse_mapping(mapping) if mapping else None,
            pattern=pattern,
            replacement=get_option(options, "replacement") or "",
        )
        count = run(
            "rename",
            cfg,
            open_source(fromfile, options),
            get_option(options, "output"),
            engine=get_option(options, "engine") or "auto",
        )
        logger.debug("rename: wrote %d records", count)
