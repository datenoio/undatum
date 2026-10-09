"""Row operations: rename, fill, replace, search, head.

Each operation has a Python implementation that streams records and, where the result
is guaranteed to be identical, a DuckDB form used for DuckDB-readable inputs.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import Any

from .base import Operation, Streaming, literal, quote, register
from .spill import reversed_rows

TEXT_TYPES = ("VARCHAR",)


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


# ---------------------------------------------------------------------------- rename


@dataclass(frozen=True)
class RenameConfig:
    """Rename fields by exact mapping and/or a regular expression.

    Args:
        mapping: Old name -> new name.
        pattern: Regular expression applied to every field name (after ``mapping``).
        replacement: Replacement for ``pattern`` (``re.sub`` syntax).
    """

    mapping: dict[str, str] | None = None
    pattern: str | None = None
    replacement: str = ""

    def new_name(self, name: str) -> str:
        """Return the renamed field name."""
        if self.mapping and name in self.mapping:
            return self.mapping[name]
        if self.pattern:
            return re.sub(self.pattern, self.replacement, name)
        return name


@register
class Rename(Operation[RenameConfig]):
    """Rename fields."""

    name = "rename"

    def apply(self, rows: Iterable[Any], cfg: RenameConfig) -> Iterator[Any]:
        names: dict[str, str] = {}
        for row in rows:
            if not isinstance(row, dict):
                yield row
                continue
            out = {}
            for key, value in row.items():
                new = names.get(key)
                if new is None:
                    new = names[key] = cfg.new_name(key)
                out[new] = value
            yield out

    def to_sql(self, source: str, schema: dict[str, str], cfg: RenameConfig) -> str | None:
        renamed = [cfg.new_name(name) for name in schema]
        if len(set(renamed)) != len(renamed):
            return None  # colliding names: Python keeps the last value, SQL would duplicate
        columns = ", ".join(
            quote(old) if old == new else f"{quote(old)} AS {quote(new)}"
            for old, new in zip(schema, renamed, strict=True)
        )
        return f"SELECT {columns} FROM {source}"


# ------------------------------------------------------------------------------ fill


@dataclass(frozen=True)
class FillConfig:
    """Fill empty values (missing, null or empty string).

    Args:
        fields: Fields to fill; every field of each record when ``None``.
        strategy: ``constant`` (use ``value``), ``forward`` (previous non-empty value) or
            ``backward`` (next non-empty value).
        value: Constant, and the fallback for ``forward``/``backward`` when no neighbour
            value exists (only when non-empty).
    """

    fields: tuple[str, ...] | None = None
    strategy: str = dc_field(
        default="constant", metadata={"choices": ("constant", "forward", "backward")}
    )
    value: Any = ""


@register
class Fill(Operation[FillConfig]):
    """Fill empty values."""

    name = "fill"

    def apply(self, rows: Iterable[Any], cfg: FillConfig) -> Iterator[Any]:
        if cfg.strategy == "backward":
            # Next non-empty value = previous one when reading the input backwards.
            filled = self._fill(reversed_rows(rows), cfg)
            yield from reversed_rows(filled)
            return
        yield from self._fill(rows, cfg)

    @staticmethod
    def _fill(rows: Iterable[Any], cfg: FillConfig) -> Iterator[Any]:
        neighbour: dict[str, Any] = {}
        for row in rows:
            if not isinstance(row, dict):
                yield row
                continue
            out = dict(row)
            for field in cfg.fields if cfg.fields is not None else list(out):
                if _is_empty(out.get(field)):
                    if cfg.strategy == "constant":
                        out[field] = cfg.value
                    elif field in neighbour:
                        out[field] = neighbour[field]
                    elif cfg.value:
                        out[field] = cfg.value
                else:
                    neighbour[field] = out[field]
            yield out

    def to_sql(self, source: str, schema: dict[str, str], cfg: FillConfig) -> str | None:
        if cfg.strategy != "constant" or not isinstance(cfg.value, str):
            return None
        targets = list(cfg.fields) if cfg.fields is not None else list(schema)
        if any(schema.get(field, "VARCHAR") not in TEXT_TYPES for field in targets):
            return None  # Python would put a string into a typed column
        parts = []
        for name in schema:
            if name in targets:
                parts.append(
                    f"COALESCE(NULLIF({quote(name)}, ''), {literal(cfg.value)}) AS {quote(name)}"
                )
            else:
                parts.append(quote(name))
        parts += [
            f"{literal(cfg.value)} AS {quote(field)}" for field in targets if field not in schema
        ]
        return f"SELECT {', '.join(parts)} FROM {source}"


# --------------------------------------------------------------------------- replace


@dataclass(frozen=True)
class ReplaceConfig:
    """Replace text in one field.

    Args:
        field: Field whose values change.
        pattern: Text (or regular expression with ``regex``) to find.
        replacement: Replacement text.
        regex: Treat ``pattern`` as a regular expression.
        global_replace: Replace every occurrence instead of the first.
    """

    field: str
    pattern: str
    replacement: str = ""
    regex: bool = False
    global_replace: bool = False


@register
class Replace(Operation[ReplaceConfig]):
    """Replace text in a field."""

    name = "replace"

    def apply(self, rows: Iterable[Any], cfg: ReplaceConfig) -> Iterator[Any]:
        count = 0 if cfg.global_replace else 1
        if cfg.regex:
            compiled = re.compile(cfg.pattern)

            def change(text: str) -> str:
                return compiled.sub(cfg.replacement, text, count=count)

        else:

            def change(text: str) -> str:
                return text.replace(cfg.pattern, cfg.replacement, -1 if count == 0 else 1)

        for row in rows:
            if isinstance(row, dict) and row.get(cfg.field) is not None:
                row = dict(row)
                row[cfg.field] = change(str(row[cfg.field]))
            yield row

    def to_sql(self, source: str, schema: dict[str, str], cfg: ReplaceConfig) -> str | None:
        if schema.get(cfg.field) not in TEXT_TYPES:
            return None
        column = quote(cfg.field)
        if not cfg.regex and cfg.global_replace:
            expr = f"replace({column}, {literal(cfg.pattern)}, {literal(cfg.replacement)})"
        else:
            if cfg.regex and ("\\g" in cfg.replacement or "(?" in cfg.pattern):
                return None  # Python-only regex syntax
            pattern = cfg.pattern if cfg.regex else re.escape(cfg.pattern)
            replacement = cfg.replacement if cfg.regex else cfg.replacement.replace("\\", "\\\\")
            flags = ", 'g'" if cfg.global_replace else ""
            expr = f"regexp_replace({column}, {literal(pattern)}, {literal(replacement)}{flags})"
        columns = ", ".join(
            f"{expr} AS {column}" if name == cfg.field else quote(name) for name in schema
        )
        return f"SELECT {columns} FROM {source}"


# ---------------------------------------------------------------------------- search


@dataclass(frozen=True)
class SearchConfig:
    """Keep records where a field matches a regular expression.

    Args:
        pattern: Regular expression (searched anywhere in the value).
        fields: Fields to search; every field when ``None``.
        ignore_case: Case-insensitive matching.
    """

    pattern: str
    fields: tuple[str, ...] | None = None
    ignore_case: bool = False


@register
class Search(Operation[SearchConfig]):
    """Filter records by a regular expression."""

    name = "search"

    def apply(self, rows: Iterable[Any], cfg: SearchConfig) -> Iterator[Any]:
        regex = re.compile(cfg.pattern, re.IGNORECASE if cfg.ignore_case else 0)
        for row in rows:
            if not isinstance(row, dict):
                continue
            fields = cfg.fields if cfg.fields is not None else row.keys()
            if any(
                row.get(field) is not None and regex.search(str(row[field])) for field in fields
            ):
                yield row

    def to_sql(self, source: str, schema: dict[str, str], cfg: SearchConfig) -> str | None:
        fields = list(cfg.fields) if cfg.fields is not None else list(schema)
        if any(schema.get(field) not in TEXT_TYPES for field in fields) or "(?" in cfg.pattern:
            return None  # str() of other types and Python-only syntax may differ from SQL
        pattern = literal(("(?i)" if cfg.ignore_case else "") + cfg.pattern)
        condition = " OR ".join(f"regexp_matches({quote(f)}, {pattern})" for f in fields)
        return f"SELECT * FROM {source} WHERE {condition or 'FALSE'}"


# ------------------------------------------------------------------------------ head


@dataclass(frozen=True)
class HeadConfig:
    """First ``limit`` records."""

    limit: int = 10


@register
class Head(Operation[HeadConfig]):
    """First records of the input; stops reading once enough are found."""

    name = "head"
    streaming = Streaming.WINDOW

    def apply(self, rows: Iterable[Any], cfg: HeadConfig) -> Iterator[Any]:
        yield from itertools.islice(rows, max(cfg.limit, 0))

    def to_sql(self, source: str, schema: dict[str, str], cfg: HeadConfig) -> str | None:
        return f"SELECT * FROM {source} LIMIT {max(int(cfg.limit), 0)}"


# ----------------------------------------------------------------------------- slice


@dataclass(frozen=True)
class SliceConfig:
    """Records by position (0-based).

    Args:
        start: First position of a range.
        end: Position after the last one of a range (exclusive); to the end when ``None``.
        indices: Explicit positions instead of a range.
    """

    start: int = 0
    end: int | None = None
    indices: frozenset[int] | None = None


@register
class Slice(Operation[SliceConfig]):
    """Records by position; reading stops after the last wanted record."""

    name = "slice"
    streaming = Streaming.WINDOW

    def apply(self, rows: Iterable[Any], cfg: SliceConfig) -> Iterator[Any]:
        if cfg.indices is not None:
            if not cfg.indices:
                return
            last = max(cfg.indices)
            for position, row in enumerate(rows):
                if position in cfg.indices:
                    yield row
                if position >= last:
                    return
            return
        yield from itertools.islice(rows, max(cfg.start, 0), cfg.end)

    def to_sql(self, source: str, schema: dict[str, str], cfg: SliceConfig) -> str | None:
        if cfg.indices is not None:
            return None
        start = max(int(cfg.start), 0)
        query = f"SELECT * FROM {source}"
        if cfg.end is not None:
            query += f" LIMIT {max(int(cfg.end) - start, 0)}"
        if start:
            query += f" OFFSET {start}"
        return query
