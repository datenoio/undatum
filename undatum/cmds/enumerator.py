"""Enum command: add row numbers, UUIDs or a constant field."""

import logging

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import EnumConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)

KINDS = ("number", "uuid", "constant")


class Enumerator:
    """Enum command handler."""

    def enum(self, fromfile, options=None):
        """Add a generated field to every record.

        Args:
            fromfile: Input path.
            options: ``field`` (default ``row_id``), ``type`` (``number``, ``uuid``,
                ``constant``), ``start``, ``value``, ``output`` and reader options.

        Raises:
            ValidationError: If the type is unknown.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        kind = get_option(options, "type") or "number"
        if kind not in KINDS:
            raise ValidationError(
                f"Unknown enum type '{kind}'", field="type", suggestions=list(KINDS)
            )
        cfg = EnumConfig(
            field=get_option(options, "field") or "row_id",
            kind=kind,
            start=int(get_option(options, "start") or 1),
            value=get_option(options, "value"),
        )
        count = run("enum", cfg, open_source(fromfile, options), get_option(options, "output"))
        logger.debug("enum: wrote %d records", count)
