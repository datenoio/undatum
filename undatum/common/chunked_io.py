"""Chunked streaming I/O utilities for constant memory usage."""

import logging
from collections.abc import Callable, Iterator
from typing import Any

logger = logging.getLogger(__name__)


def chunked_reader(iterable: Iterator[Any], chunk_size: int = 1000) -> Iterator[list[Any]]:
    """Read items from iterable in chunks.

    Args:
        iterable: Source iterable to read from
        chunk_size: Number of items per chunk

    Yields:
        Lists of items, each containing up to chunk_size items
    """
    chunk = []
    for item in iterable:
        chunk.append(item)
        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def chunked_writer(
    items: list[Any], writer_func: Callable[[list[Any]], None], chunk_size: int = 1000
) -> None:
    """Write items in chunks using provided writer function.

    Args:
        items: Items to write
        writer_func: Function that writes a chunk of items
        chunk_size: Number of items per chunk
    """
    for i in range(0, len(items), chunk_size):
        chunk = items[i : i + chunk_size]
        writer_func(chunk)


def process_chunked(
    reader: Iterator[list[Any]],
    processor: Callable[[list[Any]], list[Any]],
    writer: Callable[[list[Any]], None],
    chunk_size: int = 1000,
) -> int:
    """Process data in chunks: read, process, write.

    Args:
        reader: Iterator that yields chunks of input data
        processor: Function that processes a chunk and returns processed chunk
        writer: Function that writes a chunk of output data
        chunk_size: Number of items per chunk

    Returns:
        Total number of items processed
    """
    total_processed = 0
    for chunk in reader:
        processed_chunk = processor(chunk)
        writer(processed_chunk)
        total_processed += len(chunk)
        if total_processed % (chunk_size * 10) == 0:
            logger.debug(f"Processed {total_processed} items")
    return total_processed
