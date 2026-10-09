"""Explode command: one record per part of a delimited field."""

import logging

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import ExplodeConfig, run
from ..utils import get_option

logger = logging.getLogger(__name__)


class Exploder:
    """Explode command handler."""

    def explode(self, fromfile, options=None):
        """Split ``field`` by ``separator`` into one record per part.

        Args:
            fromfile: Input path.
            options: ``field``, ``separator`` (default ``,``), ``output`` and reader options.

        Raises:
            ValidationError: If no field is given.
        """
        options = options or {}
        validate_file_path(fromfile, check_read=True)
        field_name = get_option(options, "field")
        if not field_name:
            raise ValidationError("explode requires a field name", field="field")
        cfg = ExplodeConfig(field=field_name, separator=get_option(options, "separator") or ",")
        count = run("explode", cfg, open_source(fromfile, options), get_option(options, "output"))
        logger.debug("explode: wrote %d records", count)
