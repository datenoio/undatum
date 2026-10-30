"""Conservative offline DuckDB compaction with catalog and typed value verification.

Adapted from filerepack/duckdb.py (Ivan Begtin, BSD-3-Clause).
The original copyright, conditions and disclaimer follow.
"""

# Copyright (c) 2018, Ivan Begtin. All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
# * Redistributions of source code must retain the above copyright notice, this
#   list of conditions and the following disclaimer.
# * Redistributions in binary form must reproduce the above copyright notice,
#   this list of conditions and the following disclaimer in the documentation
#   and/or other materials provided with the distribution.
# * Neither the name of the copyright holder nor the names of its contributors
#   may be used to endorse or promote products derived from this software
#   without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import annotations

import json
import os
import time
from collections.abc import Generator, Iterator
from contextlib import closing, contextmanager
from typing import Any

from .errors import ConfigurationError, DependencyError, UndatumError, ValidationError
from .file_snapshot import FileSnapshot
from .repack_columnar import arrow_values_equal
from .repack_types import RepackBudget, RepackError, RepackOptions, RepackPlan

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_VALUE_BYTES = 256 * 1024 * 1024
MAX_CATALOG_BYTES = 4 * 1024 * 1024
MAX_ROWS = 1_000_000
MAX_BATCH_ROWS = 1024


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _literal(path: str) -> str:
    return "'" + os.path.abspath(path).replace("'", "''") + "'"


def require_offline(*paths: str) -> None:
    """Refuse pending WALs, including those beside a symlink's actual target."""
    for path in paths:
        for resolved in {os.path.abspath(path), os.path.realpath(path)}:
            if os.path.lexists(resolved + ".wal"):
                raise ValidationError(
                    f"DuckDB WAL exists for '{path}'; close database users and recover/checkpoint "
                    "the database before repacking offline.",
                    field="input/output",
                )


def remove_candidate_sidecars(target: str) -> None:
    """Clean only the WAL owned by the private candidate, including after worker death."""
    try:
        os.unlink(target + ".wal")
    except FileNotFoundError:
        pass


def _backends() -> Any:
    try:
        import duckdb
        import pyarrow  # noqa: F401 - required for independent typed verification
    except ImportError as exc:
        raise DependencyError(
            exc.name or "duckdb", feature="DuckDB repack", install_command="pip install undatum"
        ) from exc
    return duckdb


@contextmanager
def _connection(source: str, candidate: str | None = None) -> Iterator[Any]:
    duckdb = _backends()
    require_offline(source)
    try:
        connection = duckdb.connect(
            ":memory:",
            config={
                "autoinstall_known_extensions": "false",
                "autoload_known_extensions": "false",
                "threads": "1",
                "memory_limit": "256MB",
                "temp_directory": "",
            },
        )
        try:
            connection.execute("ATTACH " + _literal(source) + " AS checked (READ_ONLY)")
            if candidate is not None:
                connection.execute("ATTACH " + _literal(candidate) + " AS candidate")
            connection.execute("SET enable_external_access=false")
            yield connection
        finally:
            connection.close()
    except duckdb.Error as exc:
        raise UndatumError(f"DuckDB repack failed: {exc}", exit_code=3) from exc


def _catalog(connection: Any) -> list[list[tuple[Any, ...]]]:
    if connection.execute(
        "SELECT count(*) FROM duckdb_constraints() "
        "WHERE database_name='checked' AND constraint_type='FOREIGN KEY'"
    ).fetchall()[0][0]:
        raise ValidationError(
            "Unsupported DuckDB foreign keys: database copy cannot reliably order their data.",
            field="input",
        )
    for function in ("duckdb_views", "duckdb_sequences", "duckdb_functions", "duckdb_types"):
        condition = "" if function == "duckdb_sequences" else " AND NOT internal"
        if connection.execute(
            f"SELECT count(*) FROM {function}() WHERE database_name='checked'{condition}"
        ).fetchall()[0][0]:
            raise ValidationError(
                "Unsupported DuckDB views, sequences, functions/macros or custom types.",
                field="input",
            )
    catalogs = (
        ("duckdb_schemas", "schema_name, comment, tags", "schema_name"),
        (
            "duckdb_tables",
            "schema_name, table_name, sql, comment, tags",
            "schema_name, table_name",
        ),
        (
            "duckdb_indexes",
            "schema_name, index_name, sql, comment, tags",
            "schema_name, index_name",
        ),
        (
            "duckdb_columns",
            "schema_name, table_name, column_name, column_index, comment, column_default, "
            "is_nullable, data_type",
            "schema_name, table_name, column_index",
        ),
    )
    records: list[list[tuple[Any, ...]]] = []
    size = 0
    for function, columns, order in catalogs:
        try:
            cursor = connection.execute(
                f"SELECT {columns} FROM {function}() WHERE database_name='checked' ORDER BY {order}"
            )
        except _backends().BinderException as exc:
            raise ConfigurationError(
                "DuckDB lacks required repack catalog APIs; upgrade the duckdb package."
            ) from exc
        rows: list[tuple[Any, ...]] = []
        while batch := cursor.fetchmany(128):
            size += len(json.dumps(batch, ensure_ascii=True, sort_keys=True).encode("ascii"))
            if size > MAX_CATALOG_BYTES:
                raise ValidationError("DuckDB catalog exceeds the supported 4 MiB limit.")
            rows.extend(batch)
        records.append(rows)
    return records


def _arrow_type(dtype: Any) -> bool:
    import pyarrow as pa

    if (
        pa.types.is_list(dtype)
        or pa.types.is_large_list(dtype)
        or pa.types.is_fixed_size_list(dtype)
    ):
        return _arrow_type(dtype.value_type)
    if pa.types.is_struct(dtype):
        return all(_arrow_type(field.type) for field in dtype)
    if pa.types.is_map(dtype):
        return _arrow_type(dtype.key_type) and _arrow_type(dtype.item_type)
    return any(
        check(dtype)
        for check in (
            pa.types.is_boolean,
            pa.types.is_integer,
            pa.types.is_floating,
            pa.types.is_decimal,
            pa.types.is_string,
            pa.types.is_large_string,
            pa.types.is_binary,
            pa.types.is_large_binary,
            pa.types.is_date,
            pa.types.is_time,
            pa.types.is_timestamp,
            pa.types.is_null,
        )
    )


def _reader(connection: Any, table: str, batch_size: int, *, empty: bool = False) -> Any:
    # A relation streams record batches (DuckDB 1.5 and 2.0); 2.0 copies execute() results.
    query = "SELECT * FROM checked." + table + (" LIMIT 0" if empty else "")
    reader = connection.sql(query).to_arrow_reader(batch_size)
    if not all(_arrow_type(field.type) for field in reader.schema):
        reader.close()
        raise ValidationError("Unsupported DuckDB Arrow column type.", field="input")
    return reader


def prepare_duckdb(source: str, options: RepackOptions) -> None:
    """Validate controls, dependencies and the supported database profile before staging."""
    if options.compression is not None and (
        not isinstance(options.compression, str) or options.compression.lower() != "auto"
    ):
        raise ValidationError(
            "DuckDB repack supports automatic compression only.", field="compression"
        )
    if options.level is not None:
        raise ValidationError(
            "DuckDB chooses internal compression levels automatically.", field="level"
        )
    if options.threads != 1:
        raise ValidationError("DuckDB repack currently uses one engine thread.", field="threads")
    if os.path.getsize(source) > MAX_FILE_BYTES:
        raise ValidationError("DuckDB exceeds the supported 256 MiB input limit.", field="input")
    with _connection(source) as connection:
        rows = 0
        for schema, table, *_rest in _catalog(connection)[1]:
            name = _quote(schema) + "." + _quote(table)
            rows += connection.execute("SELECT count(*) FROM checked." + name).fetchall()[0][0]
            if rows > MAX_ROWS:
                raise ValidationError("DuckDB exceeds the supported 1,000,000 row limit.")
            with _reader(connection, name, MAX_BATCH_ROWS, empty=True):
                pass


def _batches(connection: Any, name: str, options: RepackOptions) -> Generator[Any, None, None]:
    with _reader(connection, name, min(options.batch_size, MAX_BATCH_ROWS)) as reader:
        for batch in reader:
            batch.validate(full=True)
            yield batch


def _rewrite(source: str, target: str, budget: RepackBudget) -> None:
    # Accept either an absent stage or an allocated empty file; DuckDB needs an absent path.
    try:
        os.unlink(target)
    except FileNotFoundError:
        pass
    with _connection(source, target) as connection:
        connection.execute("COPY FROM DATABASE checked TO candidate")
        budget.check()  # Include the owned WAL before checkpoint removes it.
        connection.execute("CHECKPOINT candidate")
        budget.check()


def _compare_batches(
    left: Iterator[Any], right: Iterator[Any], usage: list[int], budget: RepackBudget
) -> None:
    original, candidate = next(left, None), next(right, None)
    while original is not None and candidate is not None:
        if not original.schema.equals(candidate.schema, check_metadata=True):
            raise RepackError("Candidate changed the DuckDB Arrow schema.")
        count = min(original.num_rows, candidate.num_rows)
        before, after = original.slice(0, count), candidate.slice(0, count)
        usage[0] += count
        usage[1] += before.nbytes
        usage[2] += after.nbytes
        budget.check(before.nbytes + after.nbytes)
        if usage[0] > MAX_ROWS or max(usage[1:]) > MAX_VALUE_BYTES:
            raise ValidationError("DuckDB typed verification exceeds supported row/value bounds.")
        if any(
            not arrow_values_equal(before.column(i), after.column(i))
            for i in range(before.num_columns)
        ):
            raise RepackError("Candidate changed DuckDB values or scan order.")
        original = next(left, None) if count == original.num_rows else original.slice(count)
        candidate = next(right, None) if count == candidate.num_rows else candidate.slice(count)
    if original is not None or candidate is not None:
        raise RepackError("Candidate changed DuckDB row count.")


def repack_duckdb(
    plan: RepackPlan, target: str, options: RepackOptions, budget: RepackBudget
) -> dict[str, Any]:
    """Copy a supported offline database and independently verify its finalized candidate."""
    started = time.monotonic()
    decoded, rows = 0, 0
    with _connection(plan.source) as connection:
        records = _catalog(connection)
        for schema, table, *_rest in records[1]:
            for batch in _batches(connection, _quote(schema) + "." + _quote(table), options):
                decoded += batch.nbytes
                rows += batch.num_rows
                budget.check(batch.nbytes)
                if decoded > MAX_VALUE_BYTES or rows > MAX_ROWS:
                    raise ValidationError("DuckDB source exceeds supported row/value bounds.")
    _rewrite(plan.source, target, budget)
    encode_seconds = time.monotonic() - started
    verified = time.monotonic()
    require_offline(plan.source, target)
    snapshot = FileSnapshot.capture(target, budget.check)
    with _connection(plan.source) as left, _connection(target) as right:
        if _catalog(left) != records or _catalog(right) != records:
            raise RepackError("Candidate changed the DuckDB catalog or metadata.")
        usage = [0, 0, 0]
        for schema, table, *_rest in records[1]:
            name = _quote(schema) + "." + _quote(table)
            with (
                closing(_batches(left, name, options)) as original,
                closing(_batches(right, name, options)) as candidate,
            ):
                _compare_batches(original, candidate, usage, budget)
        if usage[0] != rows:
            raise RepackError("DuckDB source row count changed during repacking.")
    require_offline(plan.source, target)
    snapshot.require_unchanged(check=budget.check)
    return {
        "rows": rows,
        "decoded_bytes": decoded,
        "verification": {
            "method": "duckdb-catalog-typed-values",
            "passed": True,
            "candidate_sha256": snapshot.digest,
            "duckdb_version": _backends().__version__,
        },
        "timings": {
            "encode_seconds": encode_seconds,
            "verify_seconds": time.monotonic() - verified,
        },
    }
