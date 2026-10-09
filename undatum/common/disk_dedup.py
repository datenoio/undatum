"""Disk-backed exact deduplication for large record streams."""

from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
from collections.abc import Callable, Iterable, Iterator
from typing import Any

import orjson

logger = logging.getLogger(__name__)


def key_blob(key: Any) -> bytes:
    """Serialize a dedup key to a stable bytes value for SQLite storage."""
    return orjson.dumps(key, default=str)


class DiskDeduplicator:
    """Exact deduplication with keys (and optionally rows) stored on disk."""

    def __init__(self, keep: str = "first", temp_dir: str | None = None):
        self.keep = keep if keep in ("first", "last") else "first"
        self._fd, self._path = tempfile.mkstemp(
            prefix="undatum_dedup_", suffix=".sqlite", dir=temp_dir
        )
        os.close(self._fd)
        self._conn = sqlite3.connect(self._path)
        self._conn.execute("PRAGMA journal_mode=OFF")
        self._conn.execute("PRAGMA synchronous=OFF")
        self._conn.execute("CREATE TABLE seen (key BLOB PRIMARY KEY, row BLOB)")
        self._conn.commit()
        self._count_in = 0
        self._count_unique = 0

    def process(self, records: Iterable[dict], key_fn: Callable[[dict], Any]) -> Iterator[dict]:
        """Consume records and yield unique rows according to keep policy.

        For ``keep='first'``, rows are yielded as soon as a new key is seen.
        For ``keep='last'``, rows are yielded after the full pass.
        """
        if self.keep == "first":
            yield from self._process_first(records, key_fn)
        else:
            yield from self._process_last(records, key_fn)

    def _process_first(
        self, records: Iterable[dict], key_fn: Callable[[dict], Any]
    ) -> Iterator[dict]:
        for record in records:
            self._count_in += 1
            key = key_blob(key_fn(record))
            cur = self._conn.execute("SELECT 1 FROM seen WHERE key = ? LIMIT 1", (key,))
            if cur.fetchone() is None:
                self._conn.execute("INSERT INTO seen(key, row) VALUES (?, ?)", (key, b""))
                self._count_unique += 1
                if self._count_in % 100000 == 0:
                    self._conn.commit()
                    logger.debug(
                        "disk_dedup: processed %d, unique %d",
                        self._count_in,
                        self._count_unique,
                    )
                yield record
        self._conn.commit()

    def _process_last(
        self, records: Iterable[dict], key_fn: Callable[[dict], Any]
    ) -> Iterator[dict]:
        for record in records:
            self._count_in += 1
            key = key_blob(key_fn(record))
            payload = orjson.dumps(record, default=str)
            self._conn.execute(
                "INSERT INTO seen(key, row) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET row = excluded.row",
                (key, payload),
            )
            if self._count_in % 100000 == 0:
                self._conn.commit()
                logger.debug("disk_dedup: processed %d (keep=last)", self._count_in)
        self._conn.commit()
        cur = self._conn.execute("SELECT row FROM seen")
        for (payload,) in cur:
            self._count_unique += 1
            yield orjson.loads(payload)

    def seed(self, entries: Iterable[tuple[bytes, Any]]) -> None:
        """Store keys (and, for ``keep='last'``, rows) already seen in memory.

        Lets a caller start in memory and move to disk once the key set grows, without
        reading the input again. ``entries`` are ``(key blob, row)`` pairs in first-seen
        order; the row is ignored for ``keep='first'``.
        """
        for key, row in entries:
            payload = orjson.dumps(row, default=str) if self.keep == "last" else b""
            self._conn.execute("INSERT INTO seen(key, row) VALUES (?, ?)", (key, payload))
            self._count_unique += 1
        self._conn.commit()

    @property
    def stats(self) -> tuple[int, int]:
        return self._count_in, self._count_unique

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            os.unlink(self._path)
        except OSError:
            pass

    def __enter__(self) -> DiskDeduplicator:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
