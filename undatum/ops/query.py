"""Query-style operations: sort, select, sample, mask, join."""

from __future__ import annotations

import random
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from ..utils import field_values, select_fields
from .base import Operation, Streaming, quote, register
from .structure import reiterable

# ------------------------------------------------------------------------------ sort


@dataclass(frozen=True)
class SortConfig:
    """Order records by fields.

    Args:
        by: Sort fields, most significant first.
        desc: Descending order.
        numeric: Fields compared as numbers (values that are not numbers sort last).
        memory_rows: Records sorted in memory before an external merge sort on disk.
        temp_dir: Directory for merge runs.
    """

    by: tuple[str, ...]
    desc: bool = False
    numeric: tuple[str, ...] = ()
    memory_rows: int = 100_000
    temp_dir: str | None = None


def sort_key(row: Any, cfg: SortConfig) -> tuple[Any, ...]:
    """Total, null-safe sort key: missing values sort last; numbers before text."""
    if not isinstance(row, dict):
        return ((2, 0, ""),)
    key: list[tuple[int, int, Any]] = []
    for field in cfg.by:
        found = field_values(row, field)
        value = found[0] if found else None
        if value is None or value == "" and field in cfg.numeric:
            key.append((1, 0, ""))
            continue
        if field in cfg.numeric:
            try:
                key.append((0, 0, float(value)))
            except (TypeError, ValueError):
                key.append((1, 0, str(value)))
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            key.append((0, 0, value))
        else:
            key.append((0, 1, str(value)))
    return tuple(key)


@register
class Sort(Operation[SortConfig]):
    """Stable sort; above ``memory_rows`` records it becomes an external merge sort."""

    name = "sort"
    streaming = Streaming.FULL

    def apply(self, rows: Iterable[Any], cfg: SortConfig) -> Iterator[Any]:
        from ..common.external_sort import DEFAULT_RUN_SIZE, external_merge_sort

        def key(row: Any) -> tuple[Any, ...]:
            return sort_key(row, cfg)

        iterator = iter(rows)
        buffered: list[Any] = []
        for row in iterator:
            buffered.append(row)
            if len(buffered) > cfg.memory_rows:
                stream = _chain(buffered, iterator)
                yield from external_merge_sort(
                    stream,
                    key,
                    reverse=cfg.desc,
                    run_size=min(cfg.memory_rows, DEFAULT_RUN_SIZE),
                    temp_dir=cfg.temp_dir,
                )
                return
        buffered.sort(key=key, reverse=cfg.desc)
        yield from buffered


def _chain(first: list[Any], rest: Iterator[Any]) -> Iterator[Any]:
    yield from first
    first.clear()
    yield from rest


# ---------------------------------------------------------------------------- select


@dataclass(frozen=True)
class SelectConfig:
    """Keep some fields and, optionally, the records matching a filter.

    Args:
        fields: Fields to keep (dotted paths keep nested values); all when empty.
        filter: Comparison expression such as ``age > 30 AND city == "Berlin"``.
    """

    fields: tuple[str, ...] = ()
    filter: str | None = None


@register
class Select(Operation[SelectConfig]):
    """Projection and filtering."""

    name = "select"

    def apply(self, rows: Iterable[Any], cfg: SelectConfig) -> Iterator[Any]:
        from ..common.filter import match_filter

        paths = [field.split(".") for field in cfg.fields]
        for row in rows:
            if not isinstance(row, dict):
                continue
            if cfg.filter and not match_filter(row, cfg.filter):
                continue
            yield select_fields(row, paths) if paths else row

    def to_sql(self, source: str, schema: dict[str, str], cfg: SelectConfig) -> str | None:
        from ..common.filter import translate_filter_to_sql

        if any(field not in schema for field in cfg.fields):
            return None  # dotted paths and missing fields: Python semantics
        if cfg.filter and any(not t.startswith("VARCHAR") for t in schema.values()):
            return None  # the Python filter compares text and numbers loosely
        columns = ", ".join(quote(f) for f in cfg.fields) if cfg.fields else "*"
        query = f"SELECT {columns} FROM {source}"
        if cfg.filter:
            condition = translate_filter_to_sql(cfg.filter)
            if condition is None:
                return None
            query += f" WHERE {condition}"
        return query


# ---------------------------------------------------------------------------- sample


@dataclass(frozen=True)
class SampleConfig:
    """Random sample: ``size`` records, or ``percent`` of them.

    Args:
        size: Number of records.
        percent: Share of the records (0-100); counts the input first.
        seed: Random seed for reproducible samples.
    """

    size: int | None = None
    percent: float | None = None
    seed: int | None = None


@register
class Sample(Operation[SampleConfig]):
    """Reservoir sampling; memory holds the sample only."""

    name = "sample"
    streaming = Streaming.WINDOW

    def apply(self, rows: Iterable[Any], cfg: SampleConfig) -> Iterator[Any]:
        size = cfg.size
        if size is None:
            rows = reiterable(rows)
            total = sum(1 for _ in rows)
            size = max(1, int(total * float(cfg.percent or 0) / 100)) if total else 0
        rng = random.Random(cfg.seed)
        reservoir: list[Any] = []
        for count, row in enumerate(rows):
            if len(reservoir) < size:
                reservoir.append(row)
            else:
                j = rng.randint(0, count)
                if j < size:
                    reservoir[j] = row
        yield from reservoir


# ------------------------------------------------------------------------------ mask


@dataclass(frozen=True)
class MaskConfig:
    """Mask field values.

    Args:
        fields: Fields to mask.
        method: ``redact``, ``hash`` or ``randomize``.
        salt: Salt for ``hash``.
    """

    fields: tuple[str, ...]
    method: str = dc_field(default="redact", metadata={"choices": ("redact", "hash", "randomize")})
    salt: str | None = None


@register
class Mask(Operation[MaskConfig]):
    """Anonymise fields."""

    name = "mask"

    def apply(self, rows: Iterable[Any], cfg: MaskConfig) -> Iterator[Any]:
        from ..common.masking import mask_value

        for row in rows:
            if isinstance(row, dict):
                row = dict(row)
                for field in cfg.fields:
                    if field in row:
                        row[field] = mask_value(
                            row[field], cfg.method, field_name=field, salt=cfg.salt
                        )
            yield row


# ------------------------------------------------------------------------------ join


@dataclass(frozen=True)
class JoinConfig:
    """Join with another input on key fields.

    Args:
        right: Records of the other input (held in memory, indexed by key).
        on: Key fields (dotted paths allowed); the first field when empty.
        how: ``inner``, ``left``, ``right`` or ``full``.

    When both inputs have a field with different values, the right value is stored as
    ``<field>_2``.
    """

    right: Iterable[Any]
    on: tuple[str, ...] = ()
    how: str = dc_field(default="inner", metadata={"choices": ("inner", "left", "right", "full")})


def _join_key(row: Any, fields: tuple[str, ...]) -> Any:
    if not isinstance(row, dict):
        return None
    if not fields:
        return next(iter(row.values()), None)
    values = []
    for field in fields:
        found = field_values(row, field)
        values.append(found[0] if found else None)
    key = values[0] if len(values) == 1 else tuple(values)
    try:
        hash(key)
    except TypeError:
        return repr(key)
    return key


@register
class Join(Operation[JoinConfig]):
    """Hash join; the right input is indexed in memory."""

    name = "join"

    def apply(self, rows: Iterable[Any], cfg: JoinConfig) -> Iterator[Any]:
        index: dict[Any, list[dict[str, Any]]] = {}
        for item in cfg.right:
            if isinstance(item, dict):
                index.setdefault(_join_key(item, cfg.on), []).append(item)
        matched: set[Any] = set()
        for left in rows:
            if not isinstance(left, dict):
                continue
            key = _join_key(left, cfg.on)
            if key in index:
                matched.add(key)
                for right in index[key]:
                    out = dict(left)
                    for field, value in right.items():
                        if field not in left:
                            out[field] = value
                        elif left[field] != value:
                            out[f"{field}_2"] = value
                    yield out
            elif cfg.how in ("left", "full", "outer"):
                yield left
        if cfg.how in ("right", "full", "outer"):
            for key, items in index.items():
                if key not in matched:
                    yield from items
