"""Tests for Dataset DataFrame and typed-row interop (SDK additions)."""

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from undatum import Dataset

CSV = str(Path(__file__).parent / "fixtures" / "2cols6rows.csv")


class TestDataFrameInterop:
    def test_to_pandas(self):
        df = Dataset.read(CSV).to_pandas()
        assert df.shape[0] == 6
        assert "id" in df.columns and "name" in df.columns

    def test_to_pandas_chunked(self):
        chunks = list(Dataset.read(CSV).to_pandas(chunksize=2))
        assert len(chunks) == 3
        assert all(len(c) == 2 for c in chunks)

    def test_to_polars(self):
        pytest.importorskip("polars")
        df = Dataset.read(CSV).to_polars()
        assert df.shape[0] == 6

    def test_to_dask(self):
        pytest.importorskip("dask.dataframe")
        ddf = Dataset.read(CSV).to_dask()
        assert ddf.compute().shape[0] == 6


class TestTypedRows:
    def test_as_dataclasses(self):
        @dataclass
        class Row:
            id: str
            name: str

        rows = list(Dataset.read(CSV).as_dataclasses(Row))
        assert len(rows) == 6
        assert rows[0].name == "John"

    def test_as_pydantic(self):
        pydantic = pytest.importorskip("pydantic")

        class Row(pydantic.BaseModel):
            id: str
            name: str

        rows = list(Dataset.read(CSV).as_pydantic(Row))
        assert len(rows) == 6
        assert rows[0].id == "1"


class TestResultObjects:
    def test_stats_result(self):
        from undatum.sdk.results import StatsResult

        stats = Dataset.read(CSV).stats()
        assert isinstance(stats, StatsResult)
        assert stats.count == 6
        assert stats["count"] == 6
        assert stats.num_fields >= 1

    def test_query_result_head(self):
        from undatum.sdk.results import QueryResult

        rows = Dataset.read(CSV).head(2)
        assert isinstance(rows, QueryResult)
        assert len(rows) == 2
        assert rows.to_dicts()[0]["name"] == "John"


class TestWave3Sdk:
    def test_read_table_iterates_named_sheet(self, tmp_path):
        pytest.importorskip("openpyxl")
        from openpyxl import Workbook

        path = tmp_path / "wb.xlsx"
        wb = Workbook()
        wb.active.title = "Sheet1"
        wb.active.append(["id", "name"])
        wb.active.append([1, "Alice"])
        ws2 = wb.create_sheet("Cities")
        ws2.append(["city"])
        ws2.append(["Dushanbe"])
        wb.save(path)

        rows = list(Dataset.read(str(path), table="Cities"))
        assert rows
        assert "city" in rows[0]
        assert rows[0]["city"] == "Dushanbe"

    def test_stats_flatten_nested(self, tmp_path):
        src = tmp_path / "nested.jsonl"
        src.write_text(
            '{"name": "TJK", "capital_city": {"lat": 38.56, "lon": 68.77}}\n',
            encoding="utf8",
        )
        stats = Dataset.read(str(src)).stats(flatten_nested=True, engine="iterable")
        keys = {fd.get("key") for fd in (stats.get("debug") or {}).get("fielddata", {}).values()}
        assert "capital_city.lat" in keys

    def test_iter_flatten_nested(self, tmp_path):
        src = tmp_path / "nested.jsonl"
        src.write_text(
            '{"name": "TJK", "capital_city": {"lat": 38.56, "lon": 68.77}}\n',
            encoding="utf8",
        )
        row = Dataset.read(str(src), flatten_nested=True).head(1)[0]
        assert row["capital_city.lat"] == 38.56
        assert row["name"] == "TJK"


class TestConvertMany:
    def test_directory_to_jsonl(self, tmp_path):
        raw = tmp_path / "raw"
        out = tmp_path / "out"
        raw.mkdir()
        (raw / "one.csv").write_text("a,b\n1,2\n", encoding="utf8")
        Dataset.convert_many(str(raw), str(out), to_ext="jsonl", progress=False)
        assert (out / "one.jsonl").exists()
        assert (
            json.loads((out / "one.jsonl").read_text(encoding="utf8").splitlines()[0])["a"] == "1"
        )

    def test_filename_pattern(self, tmp_path):
        raw = tmp_path / "raw"
        out = tmp_path / "out"
        raw.mkdir()
        (raw / "one.csv").write_text("a,b\n1,2\n", encoding="utf8")
        Dataset.convert_many(
            str(raw),
            str(out),
            to_ext="jsonl",
            filename_pattern="{stem}.converted.jsonl",
            progress=False,
        )
        assert (out / "one.converted.jsonl").exists()
        assert not (out / "one.jsonl").exists()

    def test_requires_target_ext(self, tmp_path):
        from undatum.common.errors import ValidationError

        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "one.csv").write_text("a,b\n1,2\n", encoding="utf8")
        with pytest.raises(ValidationError, match="target extension"):
            Dataset.convert_many(str(raw), str(tmp_path / "out"), progress=False)


def test_chain_leaves_no_temporary_files(tmp_path, monkeypatch):
    import tempfile as _tempfile

    from undatum import Dataset

    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(_tempfile, "tempdir", str(scratch))
    source = tmp_path / "data.csv"
    source.write_text("a,b\n1,\n1,\n2,x\n", encoding="utf8")
    out = tmp_path / "out.jsonl"

    Dataset.read(str(source)).fill("b", value="0").dedup().write(str(out))

    assert out.exists()
    assert list(scratch.iterdir()) == []


def test_dataset_context_manager_removes_temp_file(tmp_path, monkeypatch):
    import tempfile as _tempfile

    from undatum import Dataset

    scratch = tmp_path / "tmp"
    scratch.mkdir()
    monkeypatch.setattr(_tempfile, "tempdir", str(scratch))
    source = tmp_path / "data.csv"
    source.write_text("a,b\n1,\n2,x\n", encoding="utf8")

    # Plans are lazy and stream between steps: no temporary file exists at any point.
    with Dataset.read(str(source)).fill("b", value="0") as filled:
        assert filled.count() == 2
        assert list(scratch.iterdir()) == []
    assert list(scratch.iterdir()) == []
