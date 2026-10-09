"""Formats recognised from a file name alone, without importing iterabledata (about 1 s)."""

from __future__ import annotations

import os

# Extension -> format id, for the formats undatum reads and writes most.
FAST_FORMATS = {
    "csv": "csv",
    "tsv": "tsv",
    "json": "json",
    "jsonl": "jsonl",
    "ndjson": "jsonl",
    "parquet": "parquet",
}
FAST_CODECS = {"gz": "gz", "zst": "zst", "zstd": "zst", "bz2": "bz2", "xz": "xz", "zip": "zip"}
# Every format in FAST_FORMATS can be written by iterabledata.
FAST_WRITABLE = frozenset(FAST_FORMATS.values())


def format_from_name(path: str) -> tuple[str, str | None] | None:
    """``(format, codec)`` from a file name such as ``data.csv.gz``, or ``None``."""
    parts = os.path.basename(path).lower().split(".")
    if len(parts) < 2:
        return None
    codec = FAST_CODECS.get(parts[-1])
    ext = parts[-2] if codec and len(parts) >= 3 else parts[-1]
    fmt = FAST_FORMATS.get(ext)
    if fmt is None:
        return None
    return fmt, codec
