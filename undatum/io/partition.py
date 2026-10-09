"""Partitioned output: one directory (Hive layout) or one file name per key value.

Hive layout writes ``<dir>/<field>=<value>/data_<n>.<ext>`` exactly like DuckDB's
``COPY ... (PARTITION_BY ...)``: values are percent-encoded (``a%2Fb``), NULL and empty values
are ``__HIVE_DEFAULT_PARTITION__``, and the partition fields are not repeated inside the files, so
DuckDB, Spark, Hive and Athena read the directory back with the key columns restored.

The flat layout (``split --fields`` without ``--hive``) writes ``<dir>/<value>.<ext>`` with
NULL and empty values named ``__null__``.

At most ``max_open_files`` files are open at once. When a new partition needs a file, the
least recently used one is closed; later records of that partition go to its next file
(``data_1.<ext>``), so any number of distinct keys works with bounded memory.
"""

from __future__ import annotations

import os
from collections import OrderedDict
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..common.errors import ValidationError
from .sink import RowSink, open_sink

HIVE_NULL = "__HIVE_DEFAULT_PARTITION__"
FLAT_NULL = "__null__"
DEFAULT_MAX_OPEN_FILES = 128
FLUSH_ROWS = 1000
MAX_BUFFERED_ROWS = 100_000
# DuckDB writes these formats natively with PARTITION_BY (not JSON as of DuckDB 1.5).
DUCKDB_FORMATS = {"parquet": "PARQUET", "csv": "CSV"}


def hive_value(value: Any) -> str:
    """The directory value of a key, encoded like DuckDB and Hive (empty counts as NULL)."""
    if value is None or value == "":
        return HIVE_NULL
    return quote(str(value), safe="-_.~")


def flat_value(value: Any) -> str:
    """The file-name part of a key for the flat layout."""
    if value is None or value == "":
        return FLAT_NULL
    return quote(str(value), safe="-_.~ ,()@+")


def check_output_directory(directory: str) -> None:
    """Refuse to mix new partitions with files already in ``directory``.

    Raises:
        ValidationError: If ``directory`` is a file or a non-empty directory.
    """
    if os.path.isfile(directory):
        raise ValidationError(
            f"{directory} is a file; partitioned output needs a directory", field="output"
        )
    if os.path.isdir(directory) and any(os.scandir(directory)):
        raise ValidationError(
            f"Output directory {directory} is not empty; remove it or choose another",
            field="output",
        )


class PartitionedWriter:
    """Write records into one file per key with a bounded number of open files.

    Args:
        directory: Output directory (created when missing).
        fields: Partition fields (top-level names), outermost first.
        format_out: Output format id (``csv``, ``jsonl``, ``parquet``, ...).
        hive: Hive ``field=value`` directories (else flat ``<value>.<ext>`` names).
        max_open_files: Files open at the same time.
        keep_fields: Keep the partition fields inside the files (default: not in Hive layout,
            yes in the flat layout).
    """

    def __init__(
        self,
        directory: str,
        fields: list[str],
        format_out: str,
        *,
        hive: bool = True,
        max_open_files: int = DEFAULT_MAX_OPEN_FILES,
        keep_fields: bool | None = None,
    ) -> None:
        if not fields:
            raise ValidationError("partitioning needs at least one field", field="fields")
        if max_open_files < 1:
            raise ValidationError("--max-open-files must be at least 1", field="max_open_files")
        self.directory = Path(directory)
        self.fields = list(fields)
        self.format_out = format_out
        self.extension = format_out
        self.hive = hive
        self.max_open_files = max_open_files
        self.keep_fields = (not hive) if keep_fields is None else keep_fields
        self.columns: dict[str, None] = {}
        self._buffers: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        self._buffered = 0
        self._open: OrderedDict[tuple[Any, ...], RowSink] = OrderedDict()
        self._parts: dict[tuple[Any, ...], int] = {}
        self.records = 0
        self.files: list[str] = []

    def path_for(self, key: tuple[Any, ...], part: int) -> Path:
        """The file of the ``part``-th writer of ``key``."""
        if self.hive:
            parts = [
                f"{field}={hive_value(value)}"
                for field, value in zip(self.fields, key, strict=True)
            ]
            return self.directory.joinpath(*parts, f"data_{part}.{self.extension}")
        stem = "_".join(flat_value(value) for value in key)
        suffix = f"_{part}" if part else ""
        return self.directory / f"{stem}{suffix}.{self.extension}"

    def write(self, row: Any) -> None:
        """Add one record (records that are not dicts are ignored)."""
        if not isinstance(row, dict):
            return
        if not self.records:
            missing = [field for field in self.fields if field not in row]
            if missing:
                raise ValidationError(
                    f"Partition field(s) not found: {', '.join(missing)}",
                    field="fields",
                    suggestions=list(row),
                )
        key = tuple(row.get(field) for field in self.fields)
        if not self.keep_fields:
            row = {k: v for k, v in row.items() if k not in self.fields}
        for column in row:
            if column not in self.columns:
                self.columns[column] = None
        buffer = self._buffers.setdefault(key, [])
        buffer.append(row)
        self._buffered += 1
        self.records += 1
        if len(buffer) >= FLUSH_ROWS:
            self._flush(key)
        elif self._buffered >= MAX_BUFFERED_ROWS:
            for pending in sorted(self._buffers, key=lambda k: -len(self._buffers[k])):
                self._flush(pending)
                if self._buffered < MAX_BUFFERED_ROWS // 2:
                    break

    def write_all(self, rows: Iterable[Any]) -> int:
        """Write every record, close the files, and return the number of records."""
        try:
            for row in rows:
                self.write(row)
        except BaseException:
            self.abort()
            raise
        self.close()
        return self.records

    def _flush(self, key: tuple[Any, ...]) -> None:
        rows = self._buffers.pop(key, None)
        if not rows:
            return
        self._buffered -= len(rows)
        self._sink(key).write_batch(rows)

    def _sink(self, key: tuple[Any, ...]) -> RowSink:
        sink = self._open.get(key)
        if sink is not None:
            self._open.move_to_end(key)
            return sink
        while len(self._open) >= self.max_open_files:
            old_key, old_sink = self._open.popitem(last=False)
            old_sink.close()
        part = self._parts.get(key, 0)
        self._parts[key] = part + 1
        path = self.path_for(key, part)
        path.parent.mkdir(parents=True, exist_ok=True)
        sink = open_sink(str(path), format_out=self.format_out, fieldnames=list(self.columns))
        self._open[key] = sink
        self.files.append(str(path))
        return sink

    def close(self) -> None:
        """Flush every buffer and close every file."""
        for key in list(self._buffers):
            self._flush(key)
        while self._open:
            _, sink = self._open.popitem(last=False)
            sink.close()

    def abort(self) -> None:
        """Discard the files that are still open (closed partitions stay on disk)."""
        self._buffers.clear()
        while self._open:
            _, sink = self._open.popitem(last=False)
            sink.abort()


def duckdb_partitioned_copy(
    conn: Any,
    query: str,
    directory: str,
    fields: list[str],
    format_out: str,
    max_open_files: int = DEFAULT_MAX_OPEN_FILES,
) -> bool:
    """Write ``query`` Hive-partitioned with DuckDB ``COPY``; ``False`` when not possible."""
    native = DUCKDB_FORMATS.get(format_out)
    if native is None:
        return False
    described = conn.sql(f"DESCRIBE {query}").fetchall()
    columns = [str(row[0]) for row in described]
    missing = [field for field in fields if field not in columns]
    if missing:
        raise ValidationError(
            f"Partition field(s) not found: {', '.join(missing)}",
            field="partition_by",
            suggestions=columns,
        )
    if native != "PARQUET" and any(
        str(row[1]).upper().startswith(("DATE", "TIME", "TIMESTAMP", "INTERVAL"))
        for row in described
    ):
        return False  # DuckDB formats dates differently from the Python writer in text
    types = {str(row[0]): str(row[1]).upper() for row in described}
    # Empty text goes to the NULL partition, as in the Python writer (and Spark).
    text_keys = [f for f in fields if types[f] == "VARCHAR"]
    if text_keys:
        replaced = ", ".join(f"nullif({_quote(f)}, '') AS {_quote(f)}" for f in text_keys)
        query = f"SELECT * REPLACE ({replaced}) FROM ({query})"
    options = [f"FORMAT {native}", f"PARTITION_BY ({', '.join(_quote(f) for f in fields)})"]
    if native == "CSV":
        options.append("HEADER")
    conn.execute(f"SET partitioned_write_max_open_files = {int(max_open_files)}")
    target = directory.replace("'", "''")
    try:
        conn.execute(f"COPY ({query}) TO '{target}' ({', '.join(options)})")
    except Exception:
        _remove_contents(directory)  # it was empty or missing before (check_output_directory)
        raise
    return True


def _remove_contents(directory: str) -> None:
    import shutil

    if os.path.isdir(directory):
        for entry in os.scandir(directory):
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path)
            else:
                os.remove(entry.path)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'
