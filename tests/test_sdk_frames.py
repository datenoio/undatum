"""DataFrames of any library in and out of the SDK, through Arrow and Narwhals."""

from __future__ import annotations

import datetime
import logging

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from undatum import Dataset
from undatum.common.errors import DependencyError, UndatumError

DATA = {
    "id": [1, 2, 3, 4],
    "city": ["Berlin", "Paris", "Berlin", None],
    "amount": [1.5, None, 3.0, 4.0],
    "day": [datetime.date(2024, 1, d) for d in (1, 2, 3, 4)],
}


def _pandas():
    pd = pytest.importorskip("pandas")
    return pd.DataFrame(DATA)


def _polars():
    pl = pytest.importorskip("polars")
    return pl.DataFrame(DATA)


def _polars_lazy():
    return _polars().lazy()


def _duckdb_relation():
    return duckdb.from_arrow(pa.table(DATA))


FRAMES = {
    "pyarrow": lambda: pa.table(DATA),
    "pandas": _pandas,
    "polars": _polars,
    "polars-lazy": _polars_lazy,
    "duckdb": _duckdb_relation,
}


@pytest.fixture(params=list(FRAMES))
def frame(request):
    return FRAMES[request.param]()


def _plans(ds):
    return {
        "count": ds.count(),
        "head": ds.head(2),
        "frequency": ds.frequency("city"),
        "uniq": ds.uniq("city"),
        "filter": ds.filter(query="id > 1").count(),
        "sort": ds.sort(by="amount", desc=True).head(1),
        "select": ds.select(["id", "city"]).head(4),
    }


def test_engines_agree(frame):
    table = Dataset.from_frame(frame)._spec.table
    results = {
        engine: _plans(Dataset(table=table, options={"engine": engine}))
        for engine in ("python", "auto")
    }
    assert results["auto"] == results["python"]
    assert results["auto"]["count"] == 4
    assert results["auto"]["head"][0]["city"] == "Berlin"


def test_plans_run_in_duckdb(caplog):
    with caplog.at_level(logging.DEBUG, logger="undatum.sdk.dataset"):
        Dataset.from_frame(pa.table(DATA)).frequency("city")
    assert any("DuckDB plan" in message for message in caplog.messages)


def test_write(tmp_path):
    out = tmp_path / "out.parquet"
    Dataset.from_frame(pa.table(DATA)).filter(query="id > 1").write(str(out))
    assert pq.read_table(out).column("id").to_pylist() == [2, 3, 4]


def test_stats_and_schema():
    ds = Dataset.from_frame(pa.table(DATA))
    assert ds.stats()["count"] == 4
    assert ds.schema()["id"] == {"type": "integer"}


def test_explain():
    assert Dataset.from_frame(pa.table(DATA)).limit(2).explain().startswith("read <frame>")


@pytest.mark.parametrize("backend", ["pyarrow", "pandas", "polars"])
def test_to_frame(backend):
    pytest.importorskip(backend)
    result = Dataset.from_frame(pa.table(DATA)).rename({"city": "town"}).to_frame(backend)
    import narwhals.stable.v2 as nw

    assert nw.from_native(result).to_arrow().column("town").to_pylist() == DATA["city"]
    assert type(result).__module__.split(".")[0] == backend


def test_to_frame_in_chunks():
    chunks = list(Dataset.from_frame(pa.table(DATA)).to_frame("pyarrow", chunksize=3))
    assert [chunk.num_rows for chunk in chunks] == [3, 1]


def test_csv_to_frame(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,x\n2,\n", encoding="utf8")
    table = Dataset.read(str(path)).to_frame("pyarrow")
    assert table.to_pylist() == [{"a": "1", "b": "x"}, {"a": "2", "b": ""}]


def test_narwhals_frame_is_accepted():
    import narwhals.stable.v2 as nw

    assert Dataset.from_frame(nw.from_native(pa.table(DATA))).count() == 4


def test_not_a_frame():
    with pytest.raises(UndatumError, match="Not a DataFrame"):
        Dataset.from_frame([{"a": 1}])


def test_missing_backend(monkeypatch):
    import narwhals.stable.v2 as nw

    def missing(*args, **kwargs):
        raise ModuleNotFoundError("No module named 'modin'", name="modin")

    monkeypatch.setattr(nw, "from_arrow", missing)
    with pytest.raises(DependencyError, match="modin"):
        Dataset.from_frame(pa.table(DATA)).to_frame("modin")
