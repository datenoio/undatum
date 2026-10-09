"""Replace command: replace text in a field."""

import logging
import re

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import ReplaceConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)


class Replacer:
    """Replace command handler."""

    def replace(self, fromfile, options=None):
        """Replace text (or a regular expression with ``regex``) in one field.

        Args:
            fromfile: Input path.
            options: ``field``, ``pattern``, ``replacement``, ``regex``, ``global``,
                ``output``, ``engine`` and reader options.

        Raises:
            ValidationError: If the field or pattern is missing, or the regular expression
                is invalid.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        field_name = get_option(options, "field")
        pattern = get_option(options, "pattern")
        if not field_name or not pattern:
            raise ValidationError("Field and pattern are required", field="field")
        use_regex = bool(get_option(options, "regex"))
        if use_regex:
            try:
                re.compile(pattern)
            except re.error as e:
                raise ValidationError(f"Invalid regex pattern: {e}", field="pattern") from e
        cfg = ReplaceConfig(
            field=field_name,
            pattern=pattern,
            replacement=get_option(options, "replacement") or "",
            regex=use_regex,
            global_replace=bool(get_option(options, "global")),
        )
        count = run(
            "replace",
            cfg,
            open_source(fromfile, options),
            get_option(options, "output"),
            engine=get_option(options, "engine") or "auto",
        )
        logger.debug("replace: wrote %d records", count)
