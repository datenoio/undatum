"""Disk-backed buffers for operations that need the whole input (reverse, backward fill)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable, Iterator
from typing import Any

import orjson

# Records kept in memory per chunk before spilling to disk.
DEFAULT_CHUNK_ROWS = 50_000


def _dump(record: Any) -> bytes:
    return orjson.dumps(record, default=str, option=orjson.OPT_NON_STR_KEYS)


def reversed_rows(rows: Iterable[Any], chunk_rows: int = DEFAULT_CHUNK_ROWS) -> Iterator[Any]:
    """Yield ``rows`` in reverse order with at most ``chunk_rows`` records in memory.

    Records are written to temporary JSON Lines chunks; the chunks are then read back
    last to first and each chunk is reversed in memory. Values that JSON cannot represent
    (dates, decimals) come back as strings, as they would in a JSON Lines output.

    Args:
        rows: Input records.
        chunk_rows: Records per chunk (the memory bound).

    Yields:
        The records, last first.
    """
    chunk: list[Any] = []
    spilled: list[str] = []
    try:
        for row in rows:
            chunk.append(row)
            if len(chunk) >= chunk_rows:
                spilled.append(_spill(chunk))
                chunk = []
        yield from reversed(chunk)
        chunk = []
        for path in reversed(spilled):
            with open(path, "rb") as handle:
                lines = handle.read().splitlines()
            for line in reversed(lines):
                yield orjson.loads(line)
            os.remove(path)
    finally:
        for path in spilled:
            if os.path.exists(path):
                os.remove(path)


def _spill(records: list[Any]) -> str:
    fd, path = tempfile.mkstemp(prefix="undatum-spill-", suffix=".jsonl")
    with os.fdopen(fd, "wb") as handle:
        for record in records:
            handle.write(_dump(record))
            handle.write(b"\n")
    return path
