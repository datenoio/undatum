"""Progress bars on stderr, shown only in an interactive terminal.

Bars are drawn with :mod:`rich.progress`. :class:`ProgressBar` keeps the small
tqdm-style interface the commands use (iterate over it, ``update``, ``total``,
``set_description``, ``set_postfix``, ``close``, context manager).
"""

from __future__ import annotations

import logging
import sys
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# Batch advances so per-row overhead stays negligible on large files.
_FLUSH_ITEMS = 1000
_FLUSH_SECONDS = 0.1


def is_tty() -> bool:
    """Check whether progress output goes to a terminal.

    Progress is written to stderr so that stdout stays clean for data.

    Returns:
        True if stderr is a TTY, False otherwise
    """
    return hasattr(sys.stderr, "isatty") and sys.stderr.isatty()


class ProgressBar:
    """A rich progress bar on stderr with a tqdm-like interface.

    Args:
        iterable: Optional iterable to wrap; iterating advances the bar.
        total: Expected number of items (``None`` shows an indeterminate bar).
        desc: Description shown before the bar.
        unit: Unit label shown after the counter.
        leave: Keep the finished bar on screen (``False`` removes it).
        initial: Starting count.
    """

    def __init__(
        self,
        iterable: Iterable[Any] | None = None,
        *,
        total: float | None = None,
        desc: str | None = None,
        unit: str = "items",
        leave: bool = True,
        initial: int = 0,
    ):
        from rich.console import Console
        from rich.progress import (
            BarColumn,
            MofNCompleteColumn,
            Progress,
            TextColumn,
            TimeElapsedColumn,
        )

        if total is None and iterable is not None and hasattr(iterable, "__len__"):
            total = len(iterable)  # type: ignore[arg-type]
        self._iterable = iterable
        self._progress = Progress(
            TextColumn("{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn(unit),
            TimeElapsedColumn(),
            TextColumn("{task.fields[postfix]}"),
            console=Console(file=sys.stderr),
            transient=not leave,
        )
        self._task = self._progress.add_task(desc or "", total=total, completed=initial, postfix="")
        self._pending = 0.0
        self._last_flush = time.monotonic()
        self._closed = False
        self._progress.start()

    @property
    def total(self) -> float | None:
        """Expected number of items."""
        return self._progress.tasks[0].total

    @total.setter
    def total(self, value: float | None) -> None:
        self._progress.update(self._task, total=value)

    def __iter__(self) -> Iterator[Any]:
        try:
            for item in self._iterable or ():
                yield item
                self._pending += 1
                if self._pending >= _FLUSH_ITEMS or (
                    time.monotonic() - self._last_flush >= _FLUSH_SECONDS
                ):
                    self._flush()
        finally:
            self._flush()

    def _flush(self) -> None:
        if self._pending:
            self._progress.advance(self._task, self._pending)
            self._pending = 0
        self._last_flush = time.monotonic()

    def update(self, n: float = 1) -> None:
        """Advance the bar by ``n`` items."""
        self._pending += n
        self._flush()

    def set_description(self, desc: str, refresh: bool = True) -> None:
        """Replace the description."""
        self._progress.update(self._task, description=desc)

    def set_postfix(self, postfix: dict[str, Any] | None = None, **kwargs: Any) -> None:
        """Show ``key=value`` pairs after the bar (e.g. throughput)."""
        values = {**(postfix or {}), **kwargs}
        text = ", ".join(f"{key}={value}" for key, value in values.items())
        self._progress.update(self._task, postfix=text)

    def close(self) -> None:
        """Stop drawing the bar (idempotent)."""
        if not self._closed:
            self._closed = True
            self._flush()
            self._progress.stop()

    def __enter__(self) -> ProgressBar:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class _NoProgress:
    """No-op stand-in used when progress is disabled or not in a terminal."""

    def __init__(self, iterable: Iterable[Any] | None = None, total: float | None = None):
        self._iterable = iterable
        self.total = total

    def __iter__(self) -> Iterator[Any]:
        return iter(self._iterable or [])

    def __enter__(self) -> _NoProgress:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def update(self, n: float = 1) -> None:
        return None

    def set_description(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set_postfix(self, *args: Any, **kwargs: Any) -> None:
        return None

    def close(self) -> None:
        return None


def progress(
    iterable: Iterable[Any] | None = None, *, show_progress: bool = True, **kwargs: Any
) -> ProgressBar | _NoProgress:
    """Return a progress bar on stderr that is drawn only in a terminal.

    Args:
        iterable: Optional iterable to wrap.
        show_progress: False disables the bar regardless of the terminal.
        **kwargs: ``desc``, ``total``, ``unit``, ``leave``, ``initial`` (see
            :class:`ProgressBar`).

    Returns:
        A :class:`ProgressBar`, or a no-op object with the same interface when the bar
        is disabled.
    """
    kwargs.pop("file", None)
    kwargs.pop("disable", None)
    if not show_progress or not is_tty():
        return _NoProgress(iterable, total=kwargs.get("total"))
    return ProgressBar(iterable, **kwargs)


@contextmanager
def progress_bar(
    total: int | None = None,
    desc: str | None = None,
    unit: str = "items",
    disable: bool = False,
    show_progress: bool = True,
) -> Iterator[ProgressBar | None]:
    """Create a progress bar context manager.

    Args:
        total: Total number of items (None for unknown)
        desc: Description text for progress bar
        unit: Unit label (e.g., "rows", "bytes")
        disable: If True, disable progress bar
        show_progress: If False, disable progress bar (overrides disable)

    Yields:
        Progress bar object (or None if disabled)
    """
    if not show_progress or disable or not is_tty():
        yield None
        return

    pbar = ProgressBar(total=total, desc=desc, unit=unit)
    try:
        yield pbar
    finally:
        pbar.close()


def wrap_iterable(
    iterable: Iterable[Any],
    total: int | None = None,
    desc: str | None = None,
    unit: str = "items",
    disable: bool = False,
    show_progress: bool = True,
) -> Iterator[Any]:
    """Wrap an iterable with progress indication.

    Args:
        iterable: Iterator to wrap
        total: Total number of items (None for unknown)
        desc: Description text for progress bar
        unit: Unit label (e.g., "rows", "bytes")
        disable: If True, disable progress bar
        show_progress: If False, disable progress bar (overrides disable)

    Yields:
        Items from iterable with progress tracking
    """
    if not show_progress or disable or not is_tty():
        yield from iterable
        return

    with ProgressBar(iterable, total=total, desc=desc, unit=unit) as pbar:
        yield from pbar


def update_progress(pbar: Any | None, n: int = 1) -> None:
    """Update progress bar by n items.

    Args:
        pbar: Progress bar object (from progress_bar context manager)
        n: Number of items to increment by
    """
    if pbar is not None:
        try:
            pbar.update(n)
        except Exception:
            # Best effort: never fail the command because of this step.
            logger.debug("ignoring progress display error", exc_info=True)


def set_progress_description(pbar: Any | None, desc: str) -> None:
    """Set progress bar description.

    Args:
        pbar: Progress bar object (from progress_bar context manager)
        desc: Description text
    """
    if pbar is not None:
        try:
            pbar.set_description(desc)
        except Exception:
            # Best effort: never fail the command because of this step.
            logger.debug("ignoring progress display error", exc_info=True)


def set_progress_postfix(pbar: Any | None, postfix: dict[str, Any]) -> None:
    """Set progress bar postfix (additional info like throughput).

    Args:
        pbar: Progress bar object (from progress_bar context manager)
        postfix: Dictionary of key-value pairs to display
    """
    if pbar is not None:
        try:
            pbar.set_postfix(postfix)
        except Exception:
            # Best effort: never fail the command because of this step.
            logger.debug("ignoring progress display error", exc_info=True)
