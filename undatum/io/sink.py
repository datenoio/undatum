"""Record sinks: one interface for output files (any writable format) and stdout."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

from ..common.writer import RecordSink, StdoutSink


class RowSink(Protocol):
    """What every sink offers: batches in, ``close()`` publishes, ``abort()`` discards."""

    def write_batch(self, records: list[dict[str, Any]]) -> None: ...

    def close(self) -> int | None: ...

    def abort(self) -> None: ...


class _StdoutRowSink:
    """:class:`StdoutSink` with the :class:`RowSink` interface."""

    def __init__(self, fmt: str, fieldnames: list[str] | None):
        self._sink = StdoutSink(fmt, fieldnames)

    @property
    def count(self) -> int:
        return self._sink.count

    def write_batch(self, records: Iterable[dict[str, Any]]) -> None:
        self._sink.write_batch(records)

    def close(self) -> int:
        return self._sink.close()

    def abort(self) -> None:
        # Records already on stdout cannot be taken back; finish the document.
        self._sink.close()


def stdout_format(format_out: str | None = None) -> str:
    """Format for records on stdout: ``--format-out``, then the input's text format."""
    from ..common.stdio import stdout_format as hint

    return format_out or hint.get() or "jsonl"


def open_sink(
    output: str | None,
    format_out: str | None = None,
    fieldnames: list[str] | None = None,
) -> RowSink:
    """Open a sink for ``output`` (a path or URI), or for stdout when it is empty.

    Files are written to a temporary sibling and renamed on :meth:`RowSink.close`;
    :meth:`RowSink.abort` removes the partial output.

    Args:
        output: Output path or URI; ``None``/empty writes to stdout.
        format_out: Explicit output format (else the extension, or the stdout rules).
        fieldnames: Column order for flat formats.

    Returns:
        A sink with ``write_batch``, ``close`` and ``abort``.
    """
    from ..common.stdio import format_out_override

    if output:
        return RecordSink(output, fieldnames, format_out or format_out_override.get())
    return _StdoutRowSink(stdout_format(format_out), fieldnames)
