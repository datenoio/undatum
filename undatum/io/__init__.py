"""Unified record input and output for commands, the SDK and agent tools.

- :func:`open_source` returns a lazy :class:`RowSource` (files, stdin spools, cloud and
  database URIs) that can also describe itself to DuckDB.
- :func:`open_sink` returns a :class:`RowSink` for any writable format or stdout, with
  atomic files.
"""

from .sink import RowSink, open_sink
from .source import RowSource, open_source, side_options

__all__ = ["RowSink", "RowSource", "open_sink", "open_source", "side_options"]
