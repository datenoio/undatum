"""Standard input/output support for Unix pipelines.

``-`` as an input path means standard input. The stream is spooled to a temporary
file whose extension reflects the detected format, so every command (including the
DuckDB paths, which need a file) can read it. Results written to standard output use
the input's text format unless ``--format-out`` says otherwise.
"""

from __future__ import annotations

import atexit
import contextvars
import gzip
import io
import os
import shutil
import sys
import tempfile
from typing import BinaryIO

STDIN_PATH = "-"
TEXT_FORMATS = ("csv", "tsv", "jsonl", "json")

_MAGIC_CODECS = (
    (b"\x1f\x8b", "gz"),
    (b"\x28\xb5\x2f\xfd", "zst"),
    (b"BZh", "bz2"),
    (b"\xfd7zXZ\x00", "xz"),
)

_spooled: list[str] = []


class OutputClosed(Exception):
    """The process reading our standard output went away (``| head``).

    Raised instead of :class:`BrokenPipeError` so that the CLI framework, which treats
    ``EPIPE`` as a failure, lets it reach the entry point, where it ends the run with
    exit status 0.
    """


# Format used for records written to stdout by the running command (set by the CLI).
stdout_format: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "undatum_stdout_format", default=None
)
# Explicit --format-out given on the command line (applies to --output files too).
format_out_override: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "undatum_format_out", default=None
)


@atexit.register
def _cleanup() -> None:
    for path in _spooled:
        try:
            os.remove(path)
        except OSError:
            pass


def detect_stream_format(head: bytes) -> tuple[str, str | None]:
    """Guess ``(format, codec)`` from the first bytes of a stream.

    Args:
        head: Leading bytes (a few KB is enough).

    Returns:
        A format id (``parquet``, ``json``, ``jsonl``, ``tsv`` or ``csv``) and an optional
        compression codec extension.
    """
    codec = next((name for magic, name in _MAGIC_CODECS if head.startswith(magic)), None)
    sample = head
    if codec == "gz":
        try:
            sample = gzip.GzipFile(fileobj=io.BytesIO(head)).read(4096)
        except (OSError, EOFError):
            sample = b""
    elif codec is not None:
        sample = b""  # undecodable without the full stream; default to CSV below
    if sample.startswith(b"PAR1"):
        return "parquet", codec
    text = sample.lstrip(b"\xef\xbb\xbf \t\r\n")
    if text.startswith(b"["):
        return "json", codec
    if text.startswith(b"{"):
        return "jsonl", codec
    first_line = text.split(b"\n", 1)[0]
    if first_line.count(b"\t") > first_line.count(b","):
        return "tsv", codec
    return "csv", codec


def spool_stdin(format_in: str | None = None, stream: BinaryIO | None = None) -> str:
    """Copy standard input to a temporary file and return its path.

    Args:
        format_in: Explicit input format; detected from the first bytes when omitted.
        stream: Binary stream to read (defaults to ``sys.stdin.buffer``).

    Returns:
        Path of a temporary file named after the detected format (``stdin.csv``,
        ``stdin.jsonl.gz``, ...), removed at interpreter exit.
    """
    source = stream if stream is not None else sys.stdin.buffer
    head = source.read(65536)
    detected, codec = detect_stream_format(head)
    fmt = (format_in or detected).lower()
    suffix = f".{fmt}" + (f".{codec}" if codec and not format_in else "")
    fd, path = tempfile.mkstemp(prefix="undatum-stdin-", suffix=suffix)
    with os.fdopen(fd, "wb") as target:
        target.write(head)
        shutil.copyfileobj(source, target)
    _spooled.append(path)
    return path


def text_format_of(path: str | None) -> str | None:
    """Return the text format (csv, tsv, jsonl, json) of ``path`` from its name, if any."""
    if not path:
        return None
    name = os.path.basename(path).lower()
    for codec in (".gz", ".zst", ".bz2", ".xz", ".zip", ".lz4"):
        if name.endswith(codec):
            name = name[: -len(codec)]
    ext = name.rsplit(".", 1)[-1] if "." in name else ""
    if ext == "ndjson":
        return "jsonl"
    return ext if ext in TEXT_FORMATS else None
