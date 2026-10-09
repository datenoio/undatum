"""Cat command: concatenate files by rows or by columns."""

import logging

from ..common.errors import ValidationError
from ..common.path_utils import validate_file_path
from ..io import open_source
from ..ops import CatConfig, run
from ..ops.structure import Cat as CatOperation
from ..utils import get_option

logger = logging.getLogger(__name__)


class Cat:
    """Cat command handler."""

    def cat(self, fromfiles, options=None):
        """Concatenate ``fromfiles``.

        Args:
            fromfiles: Input paths, in order.
            options: ``mode`` (``rows`` or ``columns``), ``output`` and reader options.

        Raises:
            ValidationError: If no input is given or the mode is unknown.
        """
        options = options or {}
        if not fromfiles:
            raise ValidationError("At least one input file is required", field="fromfiles")
        for fromfile in fromfiles:
            validate_file_path(fromfile, check_read=True)
        mode = get_option(options, "mode") or "rows"
        if mode not in ("rows", "columns"):
            raise ValidationError(
                f"Invalid mode: {mode}", field="mode", suggestions=["rows", "columns"]
            )
        sources = [open_source(path, options) for path in fromfiles]
        cfg = CatConfig(others=tuple(sources[1:]), mode=mode)
        # Files may have different fields; take the union so no column is dropped.
        fieldnames = CatOperation.fieldnames(sources) if mode == "rows" else None
        count = run("cat", cfg, sources[0], get_option(options, "output"), fieldnames=fieldnames)
        logger.debug("cat: wrote %d records from %d files", count, len(fromfiles))
