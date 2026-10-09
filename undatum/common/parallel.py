"""Parallel processing utilities for CPU-bound and I/O-bound workloads.

Uses a sliding window of in-flight futures so peak memory stays
O(window × chunk_size) rather than O(file size). Prefer process pools for
CPU-bound work (GIL bypass); use thread pools for I/O-bound work.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ProcessPoolExecutor,
    ThreadPoolExecutor,
    wait,
)
from typing import Any, TypeVar

from .errors import ConfigurationError

logger = logging.getLogger(__name__)

T = TypeVar("T")
R = TypeVar("R")

# Default multiplier for max in-flight chunks relative to worker count.
_DEFAULT_WINDOW_FACTOR = 2


def get_cpu_count() -> int:
    """Get number of CPU cores available.

    Returns:
        Number of CPU cores
    """
    try:
        return os.cpu_count() or 1
    except Exception:
        return 1


def is_cpu_bound_operation(operation: str) -> bool:
    """Determine if an operation is CPU-bound.

    Args:
        operation: Operation name (e.g., 'convert', 'stats', 'search')

    Returns:
        True if operation is CPU-bound, False if I/O-bound
    """
    cpu_bound_operations = {
        "convert",
        "stats",
        "frequency",
        "validate",
        "dedup",
        "search",
        "fill",
        "transform",
        "apply",
    }
    return operation.lower() in cpu_bound_operations


def resolve_worker_count(num_workers: int | None) -> int:
    """Normalize worker count; ``None`` means CPU count.

    Args:
        num_workers: Requested workers, or None for default.

    Returns:
        Effective worker count (at least 1 when parallel is intended via None).
    """
    if num_workers is None:
        return get_cpu_count()
    return max(0, int(num_workers))


def _raise_worker_error(exc: BaseException, use_processes: bool) -> None:
    """Re-raise worker failures; map pickling issues to ConfigurationError."""
    if use_processes and _is_pickle_related(exc):
        raise ConfigurationError(
            "Parallel process workers require picklable top-level callables and "
            f"payloads. Original error: {exc}"
        ) from exc
    if isinstance(exc, Exception):
        logger.error("Error in parallel processing: %s", exc)
        raise exc
    raise exc


def _is_pickle_related(exc: BaseException) -> bool:
    try:
        from pickle import PicklingError
    except ImportError:  # pragma: no cover
        PicklingError = ()  # type: ignore[misc, assignment]
    if isinstance(exc, PicklingError):
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "pickle",
            "pickling",
            "can't pickle",
            "cannot pickle",
            "not serialize",
            "serialization",
        )
    )


def parallel_map(
    func: Callable[[Any], Any],
    items: Iterable[Any],
    num_threads: int | None = None,
    use_processes: bool = False,
    chunk_size: int = 1,
    preserve_order: bool = False,
    max_in_flight: int | None = None,
) -> Iterator[Any]:
    """Apply function to items in parallel with a bounded in-flight window.

    Args:
        func: Function applied to each chunk (list of items when chunk_size > 1,
            or a single-item list / the chunk payload).
        items: Iterable of items to process.
        num_threads: Number of threads/processes (default: CPU count).
        use_processes: If True, use processes instead of threads.
        chunk_size: Number of items per worker task.
        preserve_order: If True, yield results in input chunk order.
        max_in_flight: Max concurrent chunk tasks (default: workers × 2).

    Yields:
        Results from ``func``. When ``func`` returns a list/tuple, items are
        yielded individually (unordered unless ``preserve_order`` is set at the
        chunk level — then each chunk's list is yielded as one result via
        :func:`parallel_process_chunks`).
    """
    workers = resolve_worker_count(num_threads)
    if workers <= 1:
        if chunk_size <= 1:
            for item in items:
                yield func(item)
        else:
            batch: list[Any] = []
            for item in items:
                batch.append(item)
                if len(batch) >= chunk_size:
                    result = func(batch)
                    if isinstance(result, (list, tuple)):
                        yield from result
                    else:
                        yield result
                    batch = []
            if batch:
                result = func(batch)
                if isinstance(result, (list, tuple)):
                    yield from result
                else:
                    yield result
        return

    def _chunked() -> Iterator[list[Any]]:
        batch: list[Any] = []
        for item in items:
            batch.append(item)
            if len(batch) >= chunk_size:
                yield batch
                batch = []
        if batch:
            yield batch

    for result in parallel_process_chunks(
        func,
        _chunked(),
        num_threads=workers,
        use_processes=use_processes,
        preserve_order=preserve_order,
        max_in_flight=max_in_flight,
    ):
        if isinstance(result, (list, tuple)):
            yield from result
        else:
            yield result


def parallel_process_chunks(
    processor: Callable[[Any], Any],
    chunks: Iterable[Any],
    num_threads: int | None = None,
    use_processes: bool = False,
    preserve_order: bool = False,
    max_in_flight: int | None = None,
) -> Iterator[Any]:
    """Process chunks in parallel with a sliding window of in-flight work.

    Does not materialize the full chunk stream. Peak memory is approximately
    ``max_in_flight × chunk_size × record_size``.

    Args:
        processor: Function that processes a chunk (or payload) and returns a result.
            Must be a top-level (importable) callable when ``use_processes`` is True.
        chunks: Iterable of chunks/payloads to process.
        num_threads: Number of threads/processes (default: CPU count).
        use_processes: If True, use processes instead of threads (preferred for
            CPU-bound work).
        preserve_order: If True, yield results in input order (buffers completed
            out-of-order chunks until the next sequence id is ready).
        max_in_flight: Maximum concurrent futures. Defaults to
            ``num_threads * 2``.

    Yields:
        Processed chunk results (ordered when ``preserve_order`` is True).

    Raises:
        ConfigurationError: When process workers fail due to non-picklable
            callables or payloads.
    """
    workers = resolve_worker_count(num_threads)
    chunk_iter = iter(chunks)

    if workers <= 1:
        for chunk in chunk_iter:
            yield processor(chunk)
        return

    window = (
        max_in_flight
        if max_in_flight is not None
        else max(workers * _DEFAULT_WINDOW_FACTOR, workers)
    )
    window = max(1, int(window))
    executor_class = ProcessPoolExecutor if use_processes else ThreadPoolExecutor

    try:
        with executor_class(max_workers=workers) as executor:
            yield from _drain_windowed(
                executor,
                processor,
                chunk_iter,
                window=window,
                preserve_order=preserve_order,
                use_processes=use_processes,
            )
    except ConfigurationError:
        raise
    except Exception as exc:
        _raise_worker_error(exc, use_processes)


def _drain_windowed(
    executor: Any,
    processor: Callable[[list[Any]], Any],
    chunk_iter: Iterator[list[Any]],
    *,
    window: int,
    preserve_order: bool,
    use_processes: bool,
) -> Iterator[Any]:
    """Submit chunks up to ``window`` and yield results as they complete."""
    inflight: dict[Future, int] = {}
    buffer: dict[int, Any] = {}
    next_seq = 0
    submit_seq = 0
    exhausted = False

    def _submit_one(chunk: list[Any]) -> None:
        nonlocal submit_seq
        try:
            fut = executor.submit(processor, chunk)
        except Exception as exc:
            _raise_worker_error(exc, use_processes)
        inflight[fut] = submit_seq
        submit_seq += 1

    while not exhausted and len(inflight) < window:
        try:
            chunk = next(chunk_iter)
        except StopIteration:
            exhausted = True
            break
        _submit_one(chunk)

    while inflight:
        done, _ = wait(set(inflight.keys()), return_when=FIRST_COMPLETED)
        for fut in done:
            seq = inflight.pop(fut)
            try:
                result = fut.result()
            except Exception as exc:
                _raise_worker_error(exc, use_processes)
                return  # pragma: no cover - _raise_worker_error always raises
            if preserve_order:
                buffer[seq] = result
            else:
                yield result

        if preserve_order:
            while next_seq in buffer:
                yield buffer.pop(next_seq)
                next_seq += 1

        while not exhausted and len(inflight) < window:
            try:
                chunk = next(chunk_iter)
            except StopIteration:
                exhausted = True
                break
            _submit_one(chunk)

    if preserve_order:
        while next_seq in buffer:
            yield buffer.pop(next_seq)
            next_seq += 1
