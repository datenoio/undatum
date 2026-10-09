"""Result objects returned by Dataset analysis methods."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any


class StatsResult(dict):
    """Statistics profile with both mapping and attribute access.

    Returned by ``Dataset.stats()``. Existing callers that treat the result as a
    dict keep working; attribute access is provided for the common fields.
    """

    @property
    def count(self) -> int:
        """Number of records profiled."""
        return int(self.get("count") or 0)

    @property
    def num_fields(self) -> int:
        """Number of fields found."""
        return int(self.get("num_fields") or 0)

    @property
    def fields(self) -> list[Any]:
        """Per-field statistics."""
        return list(self.get("fields") or [])

    @property
    def fieldtypes(self) -> dict[str, Any]:
        """Detected type distribution per field."""
        return dict(self.get("fieldtypes") or {})

    @property
    def dictkeys(self) -> list[Any]:
        """Fields with few distinct values (dictionary candidates)."""
        return list(self.get("dictkeys") or [])

    @property
    def debug(self) -> dict[str, Any]:
        """Engine diagnostics (timings, engine used)."""
        return dict(self.get("debug") or {})


class QueryResult(list):
    """List of records returned by Dataset query-style methods (head/tail)."""

    def to_dicts(self) -> list[dict[str, Any]]:
        """Return the records as plain dicts (non-mapping rows become ``{"value": row}``)."""
        return [dict(row) if isinstance(row, Mapping) else {"value": row} for row in self]

    def __iter__(self) -> Iterator[Any]:
        return super().__iter__()
