"""Operations that reshape the record stream: tail, enum, explode, exclude, fixlengths,
cat, reverse, transpose.

They run in Python. Multi-input operations (``cat``, ``exclude``) take their other inputs
as :class:`~undatum.io.RowSource` objects in the configuration; operations that need two
passes (``fixlengths``, ``transpose``) iterate the source twice, which works because a
``RowSource`` re-opens the input on every iteration.
"""

from __future__ import annotations

import itertools
import logging
import uuid
from collections import deque
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from ..utils import field_values
from .base import Operation, Streaming, quote, register
from .rows import TEXT_TYPES
from .spill import reversed_rows

logger = logging.getLogger(__name__)

# Position of each record in the input, added to DuckDB queries that reorder or group rows.
_ROW = "__undatum_row"
# Columns of the dedup query: a key's first position, its kept record and the record struct.
_FIRST = "__undatum_first"
_KEPT = "__undatum_kept"
_RECORD = "__undatum_record"
_DEDUP_COLUMNS = (_ROW, _FIRST, _KEPT, _RECORD)


def _numbered(source: str) -> str:
    """``source`` with each record's input position in the ``_ROW`` column."""
    # The runner keeps DuckDB's insertion order, so row_number() follows the input.
    return f"(SELECT *, row_number() OVER () AS {_ROW} FROM {source})"


def reiterable(rows: Iterable[Any]) -> Iterable[Any]:
    """Return ``rows`` if it can be iterated twice (a RowSource, a list), else a list."""
    return list(rows) if iter(rows) is rows else rows


# ------------------------------------------------------------------------------ tail


@dataclass(frozen=True)
class TailConfig:
    """Last ``limit`` records."""

    limit: int = 10


@register
class Tail(Operation[TailConfig]):
    """Last records; memory holds at most ``limit`` of them."""

    name = "tail"
    streaming = Streaming.WINDOW

    def apply(self, rows: Iterable[Any], cfg: TailConfig) -> Iterator[Any]:
        yield from deque(rows, maxlen=max(cfg.limit, 0))


# ------------------------------------------------------------------------------ enum


@dataclass(frozen=True)
class EnumConfig:
    """Add a generated value to every record.

    Args:
        field: Name of the added field (overwritten when it exists).
        kind: ``number`` (``start``, ``start + 1``, ...), ``uuid`` or ``constant``.
        start: First number.
        value: The constant for ``kind="constant"``.
    """

    field: str = "row_id"
    kind: str = dc_field(default="number", metadata={"choices": ("number", "uuid", "constant")})
    start: int = 1
    value: Any = None


@register
class Enum(Operation[EnumConfig]):
    """Number, UUID or constant column."""

    name = "enum"

    def apply(self, rows: Iterable[Any], cfg: EnumConfig) -> Iterator[Any]:
        counter = itertools.count(cfg.start)
        for row in rows:
            if isinstance(row, dict):
                row = dict(row)
                if cfg.kind == "uuid":
                    row[cfg.field] = str(uuid.uuid4())
                elif cfg.kind == "constant" and cfg.value is not None:
                    row[cfg.field] = cfg.value
                else:
                    row[cfg.field] = next(counter)
            yield row


# --------------------------------------------------------------------------- explode


@dataclass(frozen=True)
class ExplodeConfig:
    """One output record per part of a delimited field value.

    Args:
        field: Field to split.
        separator: Separator; parts are stripped of surrounding whitespace.
    """

    field: str
    separator: str = ","


@register
class Explode(Operation[ExplodeConfig]):
    """Split a field into several records."""

    name = "explode"

    def apply(self, rows: Iterable[Any], cfg: ExplodeConfig) -> Iterator[Any]:
        for row in rows:
            if not isinstance(row, dict) or row.get(cfg.field) is None:
                yield row
                continue
            for part in str(row[cfg.field]).split(cfg.separator):
                out = dict(row)
                out[cfg.field] = part.strip()
                yield out


# --------------------------------------------------------------------------- exclude


def key_of(row: Any, fields: tuple[str, ...]) -> Any:
    """Comparison key of a record: the values of ``fields`` (dotted paths allowed)."""
    if not isinstance(row, dict):
        return row
    if not fields:
        return tuple(sorted((k, repr(v)) for k, v in row.items() if v is not None))
    values = []
    for field in fields:
        found = field_values(row, field)
        values.append(found[0] if found else None)
    return tuple(values)


@dataclass(frozen=True)
class ExcludeConfig:
    """Drop records whose key appears in another input.

    Args:
        exclude: Records whose keys are excluded.
        on: Key fields (all fields when empty).
    """

    exclude: Iterable[Any]
    on: tuple[str, ...] = ()


@register
class Exclude(Operation[ExcludeConfig]):
    """Anti-join on key fields; the keys of the exclusion input are held in memory."""

    name = "exclude"

    def apply(self, rows: Iterable[Any], cfg: ExcludeConfig) -> Iterator[Any]:
        excluded = {_hashable(key_of(row, cfg.on)) for row in cfg.exclude}
        for row in rows:
            if _hashable(key_of(row, cfg.on)) not in excluded:
                yield row


def _hashable(value: Any) -> Any:
    try:
        hash(value)
        return value
    except TypeError:
        return repr(value)


# ------------------------------------------------------------------------ fixlengths


@dataclass(frozen=True)
class FixLengthsConfig:
    """Give every record the same fields.

    The field set is taken from the first ``sample`` records: all their fields, in
    alphabetical order; ``pad`` keeps as many as the widest record has, ``truncate`` as
    many as the narrowest. Missing or null values become ``value``.
    """

    strategy: str = dc_field(default="pad", metadata={"choices": ("pad", "truncate")})
    value: Any = ""
    sample: int = 1000


@register
class FixLengths(Operation[FixLengthsConfig]):
    """Normalise the field set (two passes)."""

    name = "fixlengths"

    def fieldnames(self, rows: Iterable[Any], cfg: FixLengthsConfig) -> list[str]:
        """Fields every output record gets."""
        sample = [r for r in itertools.islice(rows, cfg.sample) if isinstance(r, dict)]
        if not sample:
            return []
        sizes = [len(r) for r in sample]
        target = max(sizes) if cfg.strategy == "pad" else min(sizes)
        headers = sorted({k for r in sample for k in r if k is not None})
        return headers[:target]

    def apply(self, rows: Iterable[Any], cfg: FixLengthsConfig) -> Iterator[Any]:
        rows = reiterable(rows)
        headers = self.fieldnames(rows, cfg)
        for row in rows:
            if isinstance(row, dict):
                yield {h: row[h] if row.get(h) is not None else cfg.value for h in headers}


# ------------------------------------------------------------------------------- cat


@dataclass(frozen=True)
class CatConfig:
    """Concatenate inputs after the first one.

    Args:
        others: The other inputs, in order.
        mode: ``rows`` (one after another) or ``columns`` (side by side: record *i* of
            every input merged; shorter inputs simply end).
    """

    others: tuple[Iterable[Any], ...] = ()
    mode: str = dc_field(default="rows", metadata={"choices": ("rows", "columns")})


@register
class Cat(Operation[CatConfig]):
    """Concatenate inputs by rows or columns."""

    name = "cat"

    def apply(self, rows: Iterable[Any], cfg: CatConfig) -> Iterator[Any]:
        inputs = [rows, *cfg.others]
        if cfg.mode == "columns":
            for group in itertools.zip_longest(*inputs):
                merged: dict[str, Any] = {}
                for row in group:
                    if isinstance(row, dict):
                        merged.update(row)
                yield merged
            return
        for source in inputs:
            for row in source:
                if isinstance(row, dict):
                    yield row

    @staticmethod
    def fieldnames(inputs: Iterable[Iterable[Any]]) -> list[str]:
        """Union of the fields of the first record of every input, in order."""
        names: dict[str, None] = {}
        for source in inputs:
            first = next(iter(source), None)
            if isinstance(first, dict):
                names.update(dict.fromkeys(first))
        return list(names)


# --------------------------------------------------------------------------- reverse


@dataclass(frozen=True)
class ReverseConfig:
    """Records in reverse order."""

    chunk_rows: int = 50_000


@register
class Reverse(Operation[ReverseConfig]):
    """Reverse order; spills to disk in chunks of ``chunk_rows`` records."""

    name = "reverse"
    streaming = Streaming.FULL
    sql_holds_all_rows = True

    def apply(self, rows: Iterable[Any], cfg: ReverseConfig) -> Iterator[Any]:
        yield from reversed_rows(rows, cfg.chunk_rows)

    def to_sql(self, source: str, schema: dict[str, str], cfg: ReverseConfig) -> str | None:
        if _ROW in schema:
            return None
        return f"SELECT * EXCLUDE ({_ROW}) FROM {_numbered(source)} ORDER BY {_ROW} DESC"


# ------------------------------------------------------------------------- transpose


@dataclass(frozen=True)
class TransposeConfig:
    """Fields become records: one output record per input field.

    Each output record has ``field`` (the input field name) and ``row_0``, ``row_1``, ...
    holding that field's value in every input record.
    """

    name_field: str = "field"


@register
class Transpose(Operation[TransposeConfig]):
    """Swap rows and columns; holds one column at a time, re-reading the input per field."""

    name = "transpose"
    streaming = Streaming.FULL

    def apply(self, rows: Iterable[Any], cfg: TransposeConfig) -> Iterator[Any]:
        rows = reiterable(rows)
        fields: dict[str, None] = {}
        for row in rows:
            if isinstance(row, dict):
                fields.update(dict.fromkeys(row))
        for field in fields:
            out: dict[str, Any] = {cfg.name_field: field}
            index = 0
            for row in rows:
                if isinstance(row, dict):
                    out[f"row_{index}"] = row.get(field)
                    index += 1
            yield out


# ----------------------------------------------------------------------------- dedup


@dataclass(frozen=True)
class DedupConfig:
    """Drop records with a key already seen.

    Args:
        keys: Key fields (dotted paths allowed); every non-null field when empty.
        keep: ``first`` keeps the first record of each key, ``last`` the last one (output
            stays in order of first appearance).
        memory_keys: Unique keys kept in memory before moving to a disk index; the ``auto``
            engine deduplicates in DuckDB when the input has at most this many keys.
        low_memory: Use the disk index from the start (and the Python engine).
        temp_dir: Directory for the disk index.
    """

    keys: tuple[str, ...] = ()
    keep: str = dc_field(default="first", metadata={"choices": ("first", "last")})
    memory_keys: int = 100_000
    low_memory: bool = False
    temp_dir: str | None = None


@register
class Dedup(Operation[DedupConfig]):
    """Exact deduplication; keys are indexed in memory, then on disk."""

    name = "dedup"
    sql_holds_all_rows = True

    def apply(self, rows: Iterable[Any], cfg: DedupConfig) -> Iterator[Any]:
        from ..common.disk_dedup import DiskDeduplicator, key_blob

        def key(row: Any) -> str:
            # A str copy: orjson's bytes keep a ~1 KB buffer each, too much per key.
            return key_blob(key_of(row, cfg.keys)).decode()

        iterator = iter(rows)
        seen: dict[str, Any] = {}
        if not cfg.low_memory:
            for row in iterator:
                blob = key(row)
                if cfg.keep == "last":
                    seen[blob] = row
                elif blob not in seen:
                    seen[blob] = None
                    yield row
                if len(seen) > cfg.memory_keys:
                    break
            else:
                if cfg.keep == "last":
                    yield from seen.values()
                return
        with DiskDeduplicator(cfg.keep, cfg.temp_dir) as disk:
            disk.seed((blob.encode(), row) for blob, row in seen.items())
            seen.clear()
            yield from disk.process(iterator, key_of_fn(cfg.keys))

    def to_sql(self, source: str, schema: dict[str, str], cfg: DedupConfig) -> str | None:
        keys = list(cfg.keys) or list(schema)
        if any(name in schema for name in _DEDUP_COLUMNS):
            return None
        if any(schema.get(key) not in TEXT_TYPES for key in keys):
            return None  # dotted paths and typed values compare differently in Python
        group = ", ".join(quote(key) for key in keys)
        pick = "arg_max" if cfg.keep == "last" else "arg_min"
        # One scan: per key the kept record (as a struct of the whole row) and the position of
        # its first record, so the kept records stay in the order in which their key appeared.
        # The query holds one record per key, not the input.
        return (
            f"SELECT * EXCLUDE ({_ROW}, {_FIRST}) FROM ("
            f"SELECT unnest({_KEPT}), {_FIRST} FROM ("
            f"SELECT min({_ROW}) AS {_FIRST}, {pick}({_RECORD}, {_ROW}) AS {_KEPT} "
            f"FROM {_numbered(source)} AS {_RECORD} GROUP BY {group})"
            f") ORDER BY {_FIRST}"
        )

    def sql_fits(self, conn: Any, source: str, schema: dict[str, str], cfg: DedupConfig) -> bool:
        """Whether the input has at most ``memory_keys`` keys (estimated in one scan).

        The SQL form holds one record per key; the Python form keeps that many keys in memory
        before it moves to a disk index, so up to there both stay small.
        """
        if cfg.low_memory:
            return False
        keys = [quote(key) for key in cfg.keys or schema]
        value = keys[0] if len(keys) == 1 else f"hash({', '.join(keys)})"
        rows = conn.execute(f"SELECT approx_count_distinct({value}) FROM {source}").fetchall()
        estimate = int(rows[0][0]) if rows else 0
        logger.debug("dedup: about %d distinct keys (DuckDB up to %d)", estimate, cfg.memory_keys)
        return estimate <= cfg.memory_keys


def key_of_fn(fields: tuple[str, ...]) -> Callable[[Any], Any]:
    """``key_of`` bound to ``fields`` (for :class:`DiskDeduplicator`)."""
    return lambda row: key_of(row, fields)
