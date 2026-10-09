"""Format command module - reformat CSV with specific formatting options."""

import csv
import logging
import os
import sys

from ..common.command_utils import (
    ITERABLE_OPTIONS_KEYS,  # noqa: F401
)  # noqa: F401
from ..common.writer import resolve_output_format
from ..io import open_source
from ..ops import write_rows
from ..utils import get_option, normalize_for_json

logger = logging.getLogger(__name__)


def _is_plain_csv(path):
    """Return True for an uncompressed CSV output path (formatting options apply)."""
    from iterable.helpers.detect import detect_file_type

    if resolve_output_format(path) != "csv":
        return False
    detected = detect_file_type(path)
    ext = path.rsplit(".", 1)[-1].lower()
    return detected.get("codec") is None and ext not in ("tsv", "tab")


class Formatter:
    """Formatter command handler - reformat CSV data."""

    def __init__(self):
        pass

    def fmt(self, fromfile, options=None):
        """Reformat CSV data with specific formatting options."""
        if options is None:
            options = {}
        logger.debug("Formatting %s", fromfile)

        delimiter = get_option(options, "delimiter") or ","
        quote_style = get_option(options, "quote") or "minimal"
        escape_char = get_option(options, "escape") or "double"
        line_ending = get_option(options, "line_ending") or "unix"

        # Map quote styles
        quoting_map = {
            "always": csv.QUOTE_ALL,
            "minimal": csv.QUOTE_MINIMAL,
            "none": csv.QUOTE_NONE,
            "nonnumeric": csv.QUOTE_NONNUMERIC,
        }
        quoting = quoting_map.get(quote_style.lower(), csv.QUOTE_MINIMAL)

        # Map escape characters
        escapechar_map = {
            "double": None,  # Use double-quote escape (default CSV behavior)
            "backslash": "\\",
            "none": None,
        }
        escapechar = escapechar_map.get(escape_char.lower(), None)

        # Map line endings
        lineterminator_map = {"unix": "\n", "windows": "\r\n", "crlf": "\r\n", "mac": "\r"}
        lineterminator = lineterminator_map.get(line_ending.lower(), "\n")

        # CSV module doesn't allow escapechar when quoting is used with QUOTE_MINIMAL/QUOTE_ALL
        # Adjust based on quoting style
        if quoting in (csv.QUOTE_MINIMAL, csv.QUOTE_ALL) and escapechar == '"':
            escapechar = None  # Use double-quote escape instead

        # --delimiter sets the output dialect; the input delimiter is auto-detected.
        source = open_source(fromfile, {**options, "delimiter": None})
        # First pass: the header is every field of every record, in first-seen order.
        names: dict[str, None] = {}
        for item in source:
            if isinstance(item, dict):
                names.update(dict.fromkeys(item))
        fieldnames = list(names) or None

        to_file = get_option(options, "output")
        if to_file and not _is_plain_csv(to_file):
            # Formatting options are CSV-specific; other formats and compressed CSV are
            # written through the shared writer so the output is never silently empty.
            logger.warning("fmt: formatting options apply to plain CSV output only")
            count = write_rows(iter(source), to_file, fieldnames=fieldnames)
            logger.debug("fmt: formatted %d records", count)
            return

        target = f"{to_file}.undatum-tmp" if to_file else None
        out = open(target, "w", encoding="utf8", newline="") if target else sys.stdout
        count = 0
        try:
            if fieldnames:
                writer_kwargs = {
                    "fieldnames": fieldnames,
                    "delimiter": delimiter,
                    "quoting": quoting,
                    "lineterminator": lineterminator,
                }
                # Only add escapechar if it's not None and compatible
                if escapechar is not None and quoting in (csv.QUOTE_NONE, csv.QUOTE_NONNUMERIC):
                    writer_kwargs["escapechar"] = escapechar

                writer = csv.DictWriter(out, **writer_kwargs)
                writer.writeheader()
                for item in source:
                    if isinstance(item, dict):
                        writer.writerow(normalize_for_json(item))
                        count += 1
        except BaseException:
            if target:
                out.close()
                os.remove(target)
            raise
        if target:
            out.close()
            os.replace(target, to_file)

        logger.debug("fmt: formatted %d records", count)
