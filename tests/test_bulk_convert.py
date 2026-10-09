"""Tests for the iterabledata-backed convert/bulk_convert refactor."""

import json

import pytest

from undatum.cmds.converter import Converter
from undatum.common.command_utils import get_iterable_options


def _write_csv(path, rows="a,b\n1,2\n3,4\n"):
    path.write_text(rows)


class TestSingleConvert:
    def test_csv_to_jsonl_roundtrip(self, tmp_path):
        src = tmp_path / "in.csv"
        dst = tmp_path / "out.jsonl"
        _write_csv(src)
        Converter().convert(str(src), str(dst), {"progress": False})
        lines = [json.loads(line) for line in dst.read_text().splitlines() if line.strip()]
        assert lines == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]

    def test_csv_to_parquet_roundtrip(self, tmp_path):
        src = tmp_path / "in.csv"
        dst = tmp_path / "out.parquet"
        _write_csv(src)
        Converter().convert(str(src), str(dst), {"progress": False})
        assert dst.exists() and dst.stat().st_size > 0

    def test_parquet_row_group_size(self, tmp_path):
        pytest.importorskip("pyarrow")
        import pyarrow.parquet as pq

        src = tmp_path / "in.jsonl"
        src.write_text("".join(f'{{"id": {i}}}\n' for i in range(40)), encoding="utf8")
        dst = tmp_path / "out.parquet"
        Converter().convert(
            str(src),
            str(dst),
            {
                "row_group_size": 20,
                "batch_size": 10,
                "progress": False,
                "engine": "iterable",
                "native_batch": False,
            },
        )
        meta = pq.ParquetFile(str(dst)).metadata
        assert meta.num_rows == 40
        assert meta.num_row_groups == 2

    def test_jsonl_to_csv_roundtrip(self, tmp_path):
        src = tmp_path / "in.jsonl"
        dst = tmp_path / "out.csv"
        src.write_text('{"a": "1", "b": "2"}\n{"a": "3", "b": "4"}\n')
        Converter().convert(str(src), str(dst), {"progress": False})
        text = dst.read_text()
        assert "a" in text and "1" in text and "3" in text

    def test_csv_to_compressed_output(self, tmp_path):
        """Compressed/multi-extension outputs must not break detection (no .tmp)."""
        import gzip

        src = tmp_path / "in.csv"
        dst = tmp_path / "out.csv.gz"
        _write_csv(src)
        Converter().convert(str(src), str(dst), {"progress": False})
        assert dst.exists() and dst.stat().st_size > 0
        content = gzip.decompress(dst.read_bytes()).decode("utf-8")
        assert "1,2" in content and "3,4" in content

    def test_csv_to_gz_with_level(self, tmp_path):
        import gzip

        src = tmp_path / "in.csv"
        dst = tmp_path / "out.csv.gz"
        _write_csv(src)
        Converter().convert(str(src), str(dst), {"progress": False, "level": 1})
        content = gzip.decompress(dst.read_bytes()).decode("utf-8")
        assert "1,2" in content and "3,4" in content

    def test_csv_quotechar_roundtrip(self, tmp_path):
        src = tmp_path / "in.csv"
        dst = tmp_path / "out.jsonl"
        src.write_text("name,city\n'Alice','Dushanbe'\n", encoding="utf-8")
        Converter().convert(str(src), str(dst), {"progress": False, "quotechar": "'"})
        rows = [json.loads(line) for line in dst.read_text().splitlines() if line.strip()]
        assert rows == [{"name": "Alice", "city": "Dushanbe"}]

    def test_jsonl_to_compressed_output(self, tmp_path):
        import gzip

        src = tmp_path / "in.jsonl"
        dst = tmp_path / "out.jsonl.gz"
        src.write_text('{"a": "1", "b": "2"}\n')
        Converter().convert(str(src), str(dst), {"progress": False})
        content = gzip.decompress(dst.read_bytes()).decode("utf-8")
        assert json.loads(content.splitlines()[0]) == {"a": "1", "b": "2"}

    def test_missing_input_raises(self, tmp_path):
        from undatum.common.errors import FileNotFoundError as UndatumFileNotFound

        with pytest.raises(UndatumFileNotFound):
            Converter().convert(str(tmp_path / "nope.csv"), str(tmp_path / "out.jsonl"), {})

    @pytest.mark.parametrize("ext", ["xlsx", "xls", "ods", "xml"])
    def test_readonly_output_raises_clear_error(self, tmp_path, ext):
        """Converting to a read-only format gives an actionable ValidationError."""
        from iterable.helpers.capabilities import supports_write

        from undatum.common.errors import ValidationError

        if supports_write(ext) is not False:
            pytest.skip(f"{ext} is writable in this iterabledata version")
        src = tmp_path / "in.csv"
        _write_csv(src)
        with pytest.raises(ValidationError, match="read-only"):
            Converter().convert(str(src), str(tmp_path / f"out.{ext}"), {"progress": False})

    @pytest.mark.parametrize("ext", ["pb", "thrift", "capnp"])
    def test_schema_required_output_raises_clear_error(self, tmp_path, ext):
        """Schema-required formats (protobuf/thrift/capnp) give an actionable error."""
        from undatum.common.errors import ValidationError

        src = tmp_path / "in.csv"
        _write_csv(src)
        with pytest.raises(ValidationError, match="generic conversion target"):
            Converter().convert(str(src), str(tmp_path / f"out.{ext}"), {"progress": False})

    def test_writable_output_not_blocked(self, tmp_path):
        """A writable format with a codec suffix is not mistakenly blocked."""
        src = tmp_path / "in.csv"
        dst = tmp_path / "out.csv.gz"
        _write_csv(src)
        Converter().convert(str(src), str(dst), {"progress": False})
        assert dst.exists()


class TestResolveOutputFormat:
    def test_plain_extension(self):
        assert Converter._resolve_output_format("a/b/out.parquet", {}) == "parquet"

    def test_codec_suffix_stripped(self):
        assert Converter._resolve_output_format("out.csv.gz", {}) == "csv"
        assert Converter._resolve_output_format("out.jsonl.zst", {}) == "jsonl"

    def test_format_out_option_wins(self):
        assert Converter._resolve_output_format("out.bin", {"format_out": "JSONL"}) == "jsonl"

    def test_no_extension(self):
        assert Converter._resolve_output_format("out", {}) is None


class TestBulkConvert:
    def test_bulk_directory(self, tmp_path):
        raw = tmp_path / "raw"
        out = tmp_path / "out"
        raw.mkdir()
        _write_csv(raw / "one.csv")
        _write_csv(raw / "two.csv", "x,y\n5,6\n")
        Converter().bulk_convert(str(raw), str(out), {"progress": False}, to_ext="jsonl")
        assert (out / "one.jsonl").exists()
        assert (out / "two.jsonl").exists()
        rows = [json.loads(line) for line in (out / "one.jsonl").read_text().splitlines() if line]
        assert rows == [{"a": "1", "b": "2"}, {"a": "3", "b": "4"}]

    def test_bulk_glob(self, tmp_path):
        raw = tmp_path / "raw"
        out = tmp_path / "out"
        raw.mkdir()
        _write_csv(raw / "one.csv")
        Converter().bulk_convert(str(raw / "*.csv"), str(out), {"progress": False}, to_ext="jsonl")
        assert (out / "one.jsonl").exists()

    def test_bulk_filename_pattern(self, tmp_path):
        raw = tmp_path / "raw"
        out = tmp_path / "out"
        raw.mkdir()
        _write_csv(raw / "one.csv")
        Converter().bulk_convert(
            str(raw),
            str(out),
            {"progress": False, "filename_pattern": "{stem}.converted.jsonl"},
            to_ext="jsonl",
        )
        assert (out / "one.converted.jsonl").exists()
        assert not (out / "one.jsonl").exists()

    def test_bulk_requires_target_ext(self, tmp_path):
        from undatum.common.errors import ValidationError

        raw = tmp_path / "raw"
        raw.mkdir()
        _write_csv(raw / "one.csv")
        with pytest.raises(ValidationError, match="target extension"):
            Converter().bulk_convert(str(raw), str(tmp_path / "out"), {"progress": False})


class TestBuildConvertKwargs:
    def test_format_in_and_out_mapped(self, tmp_path):
        kwargs = Converter()._build_convert_kwargs(
            {"format_in": "jsonl", "format_out": "parquet", "compression": "snappy"},
            limit=500,
            fromfile=str(tmp_path / "data.csv"),
        )
        assert kwargs["iterableargs"]["format"] == "jsonl"
        assert kwargs["toiterableargs"]["format"] == "parquet"
        assert kwargs["toiterableargs"]["compression"] == "snappy"

    def test_start_page_mapped_to_page(self):
        kwargs = Converter()._build_convert_kwargs({"start_page": 2}, limit=100)
        assert kwargs["iterableargs"]["page"] == 2
        assert "start_page" not in kwargs["iterableargs"]

    def test_quotechar_maps_to_iterableargs(self):
        kwargs = Converter()._build_convert_kwargs({"quotechar": "'"}, limit=100)
        assert kwargs["iterableargs"]["quotechar"] == "'"
        assert kwargs["toiterableargs"]["quotechar"] == "'"

    def test_scan_limit_and_batch_size(self):
        kwargs = Converter()._build_convert_kwargs(
            {"scan_limit": 250, "batch_size": 1000, "atomic": True},
            limit=100,
        )
        assert kwargs["scan_limit"] == 250
        assert kwargs["batch_size"] == 1000
        assert kwargs["atomic"] is True

    def test_profile_maps_to_codecargs(self):
        kwargs = Converter()._build_convert_kwargs({"profile": "max"}, limit=100)
        assert kwargs["codecargs"] == {"profile": "max"}

    def test_level_maps_to_codecargs(self):
        kwargs = Converter()._build_convert_kwargs({"level": 9}, limit=100)
        assert kwargs["codecargs"] == {"compression_level": 9}

    def test_profile_and_level_codecargs(self):
        kwargs = Converter()._build_convert_kwargs({"profile": "fast", "level": 3}, limit=100)
        assert kwargs["codecargs"] == {"profile": "fast", "compression_level": 3}

    def test_invalid_profile_raises(self):
        from undatum.common.errors import ValidationError

        with pytest.raises(ValidationError, match="profile"):
            Converter()._build_convert_kwargs({"profile": "turbo"}, limit=100)

    def test_columns_and_row_range_selection(self):
        kwargs = Converter()._build_convert_kwargs(
            {"columns": "id, name", "row_range": "0:1000", "native_batch": False},
            limit=100,
        )
        assert kwargs["selection"]["columns"] == ["id", "name"]
        assert kwargs["selection"]["row_range"] == (0, 1000)
        assert kwargs["use_native_batch"] is False

    def test_native_batch_true_and_false(self):
        on = Converter()._build_convert_kwargs({"native_batch": True}, limit=100)
        off = Converter()._build_convert_kwargs({"native_batch": False}, limit=100)
        assert on["use_native_batch"] is True
        assert off["use_native_batch"] is False

    def test_native_batch_forwards_batch_size_into_selection(self):
        kwargs = Converter()._build_convert_kwargs(
            {"native_batch": True, "batch_size": 1024, "columns": "id"},
            limit=100,
        )
        assert kwargs["use_native_batch"] is True
        assert kwargs["batch_size"] == 1024
        assert kwargs["selection"]["batch_size"] == 1024
        assert kwargs["selection"]["columns"] == ["id"]

    def test_non_native_omits_selection_batch_size(self):
        kwargs = Converter()._build_convert_kwargs(
            {"native_batch": False, "batch_size": 1024}, limit=100
        )
        assert kwargs["use_native_batch"] is False
        assert "selection" not in kwargs

    def test_native_batch_auto_with_selection(self):
        kwargs = Converter()._build_convert_kwargs({"columns": "id"}, limit=100)
        assert kwargs["use_native_batch"] is True

    def test_invalid_row_range_raises(self):
        from undatum.common.errors import ValidationError

        with pytest.raises(ValidationError, match="row_range"):
            Converter()._build_convert_kwargs({"row_range": "1000"}, limit=100)

    def test_write_mode_mapped_to_toiterableargs(self):
        kwargs = Converter()._build_convert_kwargs({"write_mode": "overwrite"}, limit=100)
        assert kwargs["toiterableargs"]["write_mode"] == "overwrite"

    def test_row_group_size_mapped_to_toiterableargs(self):
        kwargs = Converter()._build_convert_kwargs({"row_group_size": 1024}, limit=100)
        assert kwargs["toiterableargs"]["row_group_size"] == 1024
        omitted = Converter()._build_convert_kwargs({}, limit=100)
        assert "row_group_size" not in omitted["toiterableargs"]

    def test_invalid_row_group_size_raises(self):
        from undatum.common.errors import ValidationError

        with pytest.raises(ValidationError, match="row_group_size"):
            Converter()._build_convert_kwargs({"row_group_size": 0}, limit=100)

    def test_use_totals_mapped(self):
        kwargs = Converter()._build_convert_kwargs({"use_totals": True}, limit=100)
        assert kwargs["use_totals"] is True

    def test_invalid_write_mode_raises(self):
        from undatum.common.errors import ValidationError

        with pytest.raises(ValidationError, match="write_mode"):
            Converter()._build_convert_kwargs({"write_mode": "merge"}, limit=100)


class TestGetIterableOptions:
    def test_start_page_alias(self):
        assert get_iterable_options({"start_page": 1}) == {"page": 1}

    def test_explicit_page_wins_over_start_page(self):
        assert get_iterable_options({"start_page": 1, "page": 3}) == {"page": 3}


class TestFormatOverrides:
    def test_format_in_on_mislabeled_file(self, tmp_path):
        src = tmp_path / "data"
        dst = tmp_path / "out.jsonl"
        src.write_text('{"a": 1}\n{"a": 2}\n')
        Converter().convert(str(src), str(dst), {"format_in": "jsonl", "progress": False})
        lines = [json.loads(line) for line in dst.read_text().splitlines() if line.strip()]
        assert lines == [{"a": 1}, {"a": 2}]

    def test_format_out_with_nonstandard_extension(self, tmp_path):
        src = tmp_path / "in.csv"
        dst = tmp_path / "out.bin"
        _write_csv(src)
        Converter().convert(
            str(src), str(dst), {"format_out": "parquet", "progress": False, "summary": False}
        )
        assert dst.exists() and dst.stat().st_size > 0
