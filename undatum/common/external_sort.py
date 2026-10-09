"""External merge sort for large record streams."""

from __future__ import annotations

import heapq
import logging
import os
import tempfile
from collections.abc import Callable, Iterable, Iterator
from typing import Any

import orjson

logger = logging.getLogger(__name__)

DEFAULT_RUN_SIZE = 50_000


def _write_run(records: list[dict], temp_dir: str) -> str:
    """Write a sorted run to a temporary JSONL file."""
    fd, path = tempfile.mkstemp(prefix="undatum_sort_", suffix=".jsonl", dir=temp_dir)
    os.close(fd)
    with open(path, "wb") as handle:
        for record in records:
            handle.write(orjson.dumps(record, default=str))
            handle.write(b"\n")
    return path


def _iter_run(path: str) -> Iterator[dict]:
    with open(path, "rb") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield orjson.loads(line)


def external_merge_sort(
    records: Iterable[dict],
    key_fn: Callable[[dict], Any],
    *,
    reverse: bool = False,
    run_size: int = DEFAULT_RUN_SIZE,
    temp_dir: str | None = None,
) -> Iterator[dict]:
    """Sort records with bounded memory via external merge sort.

    Args:
        records: Input record iterable.
        key_fn: Sort key function.
        reverse: Sort descending when True.
        run_size: Max records per in-memory run before spill.
        temp_dir: Directory for spill files (default: system temp).

    Yields:
        Sorted records.
    """
    spill_dir = tempfile.mkdtemp(prefix="undatum_sort_", dir=temp_dir)
    run_paths: list[str] = []
    chunk: list[dict] = []

    try:
        for record in records:
            chunk.append(record)
            if len(chunk) >= run_size:
                chunk.sort(key=key_fn, reverse=reverse)
                run_paths.append(_write_run(chunk, spill_dir))
                chunk = []

        if chunk:
            chunk.sort(key=key_fn, reverse=reverse)
            if not run_paths:
                # Entire input fit in one run — no merge needed.
                yield from chunk
                return
            run_paths.append(_write_run(chunk, spill_dir))

        if not run_paths:
            return

        if len(run_paths) == 1:
            yield from _iter_run(run_paths[0])
            return

        logger.debug("external_merge_sort: merging %d runs from %s", len(run_paths), spill_dir)
        yield from _merge_runs(run_paths, key_fn, reverse)
    finally:
        for path in run_paths:
            try:
                os.unlink(path)
            except OSError:
                pass
        try:
            os.rmdir(spill_dir)
        except OSError:
            pass


def _merge_runs(
    run_paths: list[str],
    key_fn: Callable[[dict], Any],
    reverse: bool,
) -> Iterator[dict]:
    """K-way merge of sorted JSONL runs."""
    iterators = [_iter_run(path) for path in run_paths]
    # heapq is min-heap; for reverse, negate by wrapping comparison via decorated keys.
    decorated: list[tuple] = []
    for idx, iterator in enumerate(iterators):
        try:
            item = next(iterator)
        except StopIteration:
            continue
        sort_key = key_fn(item)
        # For reverse, invert by storing a flag; use tuple comparison carefully.
        # Store (sort_key, idx, item) for ascending; for descending use inverted
        # by wrapping in a helper that heapq can compare via sequence number trick.
        decorated.append((sort_key, idx, item, iterator))

    if reverse:
        # Use max-heap emulation: push (-priority) doesn't work for arbitrary keys.
        # Fall back to heapq.merge with reverse via reading all iterators with key.
        streams = []
        for _sort_key, _idx, item, iterator in decorated:

            def _gen(first: Any = item, it: Iterator[Any] = iterator) -> Iterator[Any]:
                yield first
                yield from it

            streams.append(_gen())
        yield from heapq.merge(*streams, key=key_fn, reverse=True)
        return

    heap: list[tuple] = []
    for sort_key, idx, item, iterator in decorated:
        heapq.heappush(heap, (sort_key, idx, item, iterator))

    while heap:
        sort_key, idx, item, iterator = heapq.heappop(heap)
        yield item
        try:
            nxt = next(iterator)
        except StopIteration:
            continue
        heapq.heappush(heap, (key_fn(nxt), idx, nxt, iterator))
