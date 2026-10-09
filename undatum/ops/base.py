"""Operation contract and registry.

An operation is a typed configuration (a frozen dataclass) plus

- ``apply(rows, cfg)`` — a streaming Python implementation from rows to rows, and
- optionally ``to_sql(source, columns, cfg)`` — the same transformation as one DuckDB query
  over a ``FROM`` expression, used when the input is DuckDB-readable.

CLI commands, the SDK and agent tools build a config and call :func:`undatum.ops.run`.
"""

from __future__ import annotations

import enum
from collections.abc import Iterable, Iterator
from typing import Any, ClassVar, Generic, TypeVar

C = TypeVar("C")


class Streaming(enum.Enum):
    """How much of the input an operation keeps in memory."""

    ROW = "row"  # one record at a time
    WINDOW = "window"  # a bounded window (head, tail, sample)
    FULL = "full"  # needs every record; spills to disk


class Operation(Generic[C]):
    """Base class of every operation."""

    name: ClassVar[str]
    streaming: ClassVar[Streaming] = Streaming.ROW

    def apply(self, rows: Iterable[Any], cfg: C) -> Iterator[Any]:
        """Transform ``rows`` (dicts) lazily."""
        raise NotImplementedError

    def to_sql(self, source: str, schema: dict[str, str], cfg: C) -> str | None:
        """Return a DuckDB query over ``source`` (a ``FROM`` expression), or ``None``.

        Return ``None`` whenever the SQL result could differ from :meth:`apply` (for
        example a type the Python implementation treats differently); the runner then
        streams through Python.

        Args:
            source: DuckDB table expression such as ``read_parquet('x.parquet')``.
            schema: Column name -> DuckDB type, in column order.
            cfg: Operation configuration.
        """
        return None


REGISTRY: dict[str, Operation[Any]] = {}

OpClass = TypeVar("OpClass", bound=type)


def register(cls: OpClass) -> OpClass:
    """Class decorator: add an operation to :data:`REGISTRY` under its ``name``."""
    REGISTRY[cls.name] = cls()  # type: ignore[attr-defined]
    return cls


def quote(name: str) -> str:
    """Quote a column name for DuckDB."""
    return '"' + name.replace('"', '""') + '"'


def literal(value: Any) -> str:
    """Render a Python value as a DuckDB literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"
