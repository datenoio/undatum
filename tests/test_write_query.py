"""DuckDB ``COPY`` writes what the Python writer writes, for every type it is used for."""

from __future__ import annotations

from unittest import mock

import duckdb
import pytest

from undatum.common import writer
from undatum.common.writer import duckdb_copy_keeps_values
from undatum.io import RowSource
from undatum.ops.runner import write_query

# One value per DuckDB type; each query also has a NULL row.
VALUES = {
    "date": "DATE '2020-01-02'",
    "time": "TIME '10:30:00'",
    "time_fraction": "TIME '10:30:00.5'",
    "timestamp": "TIMESTAMP '2020-01-02 10:30:00'",
    "timestamp_fraction": "TIMESTAMP '2020-01-02 10:30:00.5'",
    "timetz": "TIMETZ '10:30:00+03'",
    "interval": "INTERVAL 3 DAY",
    "decimal": "1.50::DECIMAL(10,2)",
    "float": "1.1::FLOAT",
    "double": "1.1::DOUBLE",
    "bigint": "42::BIGINT",
    "hugeint": "42::HUGEINT",
    "boolean": "true",
    "uuid": "'6f1e0c4e-1c3a-4d7e-9a2b-1b2c3d4e5f60'::UUID",
    "blob": "'\\xAA'::BLOB",
    "list": "[1, 2]",
    "struct": "{'a': 1}",
    "varchar": "'x,\"y\"'",
}


def _write_both(tmp_path, expr: str, fmt: str):
    query = f"SELECT {expr} AS v, 1 AS n UNION ALL SELECT NULL, 2 ORDER BY n"
    conn = duckdb.connect()
    types = [str(row[1]) for row in conn.sql(f"DESCRIBE {query}").fetchall()]
    copied, written = tmp_path / f"copy.{fmt}", tmp_path / f"python.{fmt}"
    used_copy = write_query(conn, query, str(copied)) == -1
    with mock.patch.object(writer, "duckdb_copy_to_file", lambda *args: False):
        write_query(conn, query, str(written))
    return types, used_copy, copied, written


@pytest.mark.parametrize("fmt", ["csv", "parquet"])
@pytest.mark.parametrize("name", sorted(VALUES))
def test_copy_only_where_values_match(tmp_path, name, fmt):
    types, used_copy, copied, written = _write_both(tmp_path, VALUES[name], fmt)
    assert used_copy == duckdb_copy_keeps_values(types, fmt)
    if not used_copy:
        return
    if fmt == "csv":
        assert copied.read_bytes() == written.read_bytes()
    else:
        read = RowSource(str(copied), {"engine": "python"})
        expected = RowSource(str(written), {"engine": "python"})
        assert [dict(r) for r in read] == [dict(r) for r in expected]


def test_dates_and_timestamps_use_copy_where_they_can():
    assert duckdb_copy_keeps_values(["DATE", "BIGINT", "VARCHAR"], "csv")
    assert duckdb_copy_keeps_values(["TIMESTAMP", "DATE", "TIME"], "parquet")
    assert not duckdb_copy_keeps_values(["TIMESTAMP"], "csv")
    assert not duckdb_copy_keeps_values(["UUID"], "parquet")
    assert not duckdb_copy_keeps_values(["DATE"], "parquet", from_json=True)
