"""Table command module - pretty print data as formatted table."""

import logging

from rich.console import Console
from rich.table import Table

from ..common.command_utils import (  # noqa: F401
    ITERABLE_OPTIONS_KEYS,
    get_iterable_options,
    iter_command_rows,
)
from ..common.s3_iterable import open_path as open_iterable
from ..utils import get_option

logger = logging.getLogger(__name__)


class TableFormatter:
    """Table command handler - pretty print data."""

    def __init__(self):
        self.console = Console()

    def table(self, fromfile, options=None):
        """Display data in a formatted, aligned table."""
        if options is None:
            options = {}
        logger.debug("Processing %s", fromfile)
        iterableargs = get_iterable_options(options)
        limit = get_option(options, "limit") or 20
        fields = get_option(options, "fields")

        if fields:
            field_list = [f.strip() for f in fields.split(",")]
        else:
            field_list = None

        # First pass: collect headers and sample data
        iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
        headers = set()
        items = []
        try:
            count = 0
            for item in iter_command_rows(iterable, options):
                if count >= limit:
                    break
                if isinstance(item, dict):
                    if field_list:
                        # Filter to selected fields
                        filtered_item = {k: v for k, v in item.items() if k in field_list}
                        items.append(filtered_item)
                        headers.update(filtered_item.keys())
                    else:
                        items.append(item)
                        headers.update(item.keys())
                count += 1
        finally:
            iterable.close()

        if not items:
            print("No data to display")
            return

        # Create table
        table = Table(show_header=True, header_style="bold magenta")

        # Determine columns
        if field_list:
            columns = field_list
        else:
            columns = sorted(headers)

        # Add columns
        for col in columns:
            table.add_column(col, overflow="fold")

        # Add rows
        for item in items:
            row_values = []
            for col in columns:
                value = item.get(col, "")
                # Truncate long values
                str_value = str(value)
                if len(str_value) > 50:
                    str_value = str_value[:47] + "..."
                row_values.append(str_value)
            table.add_row(*row_values)

        # Print table
        self.console.print(table)

        if count >= limit:
            print(f"\n(Showing first {limit} rows)")
