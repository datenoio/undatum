"""Integration tests for parallel convert / DuckDB gating."""

from pathlib import Path
from unittest.mock import patch

import orjson
import pytest

from undatum.cmds.converter import Converter


@pytest.fixture
def sample_csv(tmp_path: Path) -> Path:
    path = tmp_path / "sample.csv"
    path.write_text("name,age,city\nAlice,30,NYC\nBob,25,LA\nCarol,40,SF\n", encoding="utf-8")
    return path


@pytest.fixture
def larger_csv(tmp_path: Path) -> Path:
    path = tmp_path / "larger.csv"
    lines = ["id,name,value"]
    for i in range(50):
        lines.append(f"{i},name{i},{i * 10}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def nested_jsonl(tmp_path: Path) -> Path:
    path = tmp_path / "nested.jsonl"
    rows = [
        {"id": 1, "meta": {"city": "NYC"}},
        {"id": 2, "meta": {"city": "LA"}},
        {"id": 3, "meta": {"city": "SF"}},
    ]
    with path.open("wb") as fh:
        for row in rows:
            fh.write(orjson.dumps(row) + b"\n")
    return path


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("rb") as fh:
        for line in fh:
            if line.strip():
                rows.append(orjson.loads(line))
    return rows


class _FakeConversionResult:
    rows_in = 0
    rows_out = 0
    elapsed_seconds = 0.0
    errors: list = []


class TestParallelConvert:
    def test_parallel_matches_sequential_order(self, sample_csv: Path, tmp_path: Path):
        out_seq = tmp_path / "seq.jsonl"
        out_par = tmp_path / "par.jsonl"
        conv = Converter(batch_size=2)

        conv.convert(
            str(sample_csv),
            str(out_seq),
            options={"engine": "python", "progress": False, "summary": False, "batch_size": 2},
        )
        conv.convert(
            str(sample_csv),
            str(out_par),
            options={
                "engine": "python",
                "threads": 2,
                "progress": False,
                "summary": False,
                "batch_size": 2,
            },
        )

        assert _read_jsonl(out_par) == _read_jsonl(out_seq)

    def test_parallel_larger_file_order(self, larger_csv: Path, tmp_path: Path):
        out_seq = tmp_path / "seq.jsonl"
        out_par = tmp_path / "par.jsonl"
        conv = Converter(batch_size=7)
        opts = {"engine": "python", "progress": False, "summary": False, "batch_size": 7}
        conv.convert(str(larger_csv), str(out_seq), options=opts)
        conv.convert(str(larger_csv), str(out_par), options={**opts, "threads": 3})
        assert _read_jsonl(out_par) == _read_jsonl(out_seq)

    def test_parallel_flatten_preserves_order(self, nested_jsonl: Path, tmp_path: Path):
        out_seq = tmp_path / "seq.csv"
        out_par = tmp_path / "par.csv"
        conv = Converter(batch_size=1)
        opts_base = {
            "engine": "python",
            "flatten": True,
            "progress": False,
            "summary": False,
            "batch_size": 1,
            "format_out": "csv",
        }
        conv.convert(str(nested_jsonl), str(out_seq), options=opts_base)
        conv.convert(
            str(nested_jsonl),
            str(out_par),
            options={**opts_base, "threads": 2},
        )
        assert out_par.read_text(encoding="utf-8") == out_seq.read_text(encoding="utf-8")

    def test_threads_one_uses_sequential_iterable_path(self, sample_csv: Path, tmp_path: Path):
        out = tmp_path / "out.jsonl"
        conv = Converter()
        with (
            patch.object(conv, "_convert_python_parallel") as mock_par,
            patch("iterable.convert.convert") as mock_iter,
        ):
            mock_iter.return_value = _FakeConversionResult()
            conv.convert(
                str(sample_csv),
                str(out),
                options={
                    "engine": "python",
                    "threads": 1,
                    "progress": False,
                    "summary": False,
                },
            )
            mock_par.assert_not_called()
            mock_iter.assert_called_once()

    def test_threads_gt_one_uses_parallel_path(self, sample_csv: Path, tmp_path: Path):
        out = tmp_path / "out.jsonl"
        conv = Converter()
        with patch.object(
            conv, "_convert_python_parallel", return_value=_FakeConversionResult()
        ) as mock_par:
            result = conv.convert(
                str(sample_csv),
                str(out),
                options={
                    "engine": "python",
                    "threads": 2,
                    "progress": False,
                    "summary": False,
                },
            )
            mock_par.assert_called_once()
            assert result is mock_par.return_value

    def test_low_memory_passes_smaller_window(self, sample_csv: Path, tmp_path: Path):
        out = tmp_path / "out.jsonl"
        conv = Converter()
        with patch.object(
            conv, "_convert_python_parallel", return_value=_FakeConversionResult()
        ) as mock_par:
            conv.convert(
                str(sample_csv),
                str(out),
                options={
                    "engine": "python",
                    "threads": 4,
                    "low_memory": True,
                    "progress": False,
                    "summary": False,
                },
            )
            assert mock_par.called
            options_arg = mock_par.call_args.args[4]
            assert options_arg.get("low_memory") is True

    def test_cloud_uri_skips_parallel_path(self, tmp_path: Path):
        conv = Converter()
        with (
            patch.object(conv, "_convert_python_parallel") as mock_par,
            patch("iterable.convert.convert", return_value=_FakeConversionResult()) as mock_iter,
        ):
            conv.convert(
                "s3://bucket/in.csv",
                str(tmp_path / "out.jsonl"),
                options={
                    "engine": "python",
                    "threads": 4,
                    "progress": False,
                    "summary": False,
                },
            )
            mock_par.assert_not_called()
            mock_iter.assert_called_once()

    def test_duckdb_path_skips_process_pool(self, sample_csv: Path, tmp_path: Path):
        out = tmp_path / "out.parquet"
        conv = Converter()
        with patch.object(conv, "_convert_python_parallel") as mock_par:
            result = conv.convert(
                str(sample_csv),
                str(out),
                options={
                    "engine": "duckdb",
                    "threads": 4,
                    "progress": False,
                    "summary": False,
                },
            )
            mock_par.assert_not_called()
            assert result is None or mock_par.call_count == 0

    def test_duckdb_engine_never_calls_parallel_even_on_fallback(
        self, sample_csv: Path, tmp_path: Path
    ):
        out = tmp_path / "out.jsonl"
        conv = Converter()
        with (
            patch.object(conv, "_try_duckdb_convert", return_value=False),
            patch.object(conv, "_convert_python_parallel") as mock_par,
            patch("iterable.convert.convert") as mock_iter,
        ):
            mock_iter.return_value = _FakeConversionResult()
            conv.convert(
                str(sample_csv),
                str(out),
                options={
                    "engine": "duckdb",
                    "threads": 4,
                    "progress": False,
                    "summary": False,
                },
            )
            mock_par.assert_not_called()
            mock_iter.assert_called_once()

    def test_parallel_atomic_write(self, sample_csv: Path, tmp_path: Path):
        out = tmp_path / "atomic.jsonl"
        conv = Converter(batch_size=2)
        result = conv.convert(
            str(sample_csv),
            str(out),
            options={
                "engine": "python",
                "threads": 2,
                "atomic": True,
                "progress": False,
                "summary": False,
                "batch_size": 2,
            },
        )
        assert out.exists()
        assert not (tmp_path / "atomic.jsonl.tmp").exists()
        assert result.rows_out == 3
        assert len(_read_jsonl(out)) == 3


def test_parallel_path_runs_without_fallback(larger_csv: Path, tmp_path: Path, caplog):
    """The process-pool path must not silently fall back to the sequential path."""
    out = tmp_path / "par.jsonl"
    with caplog.at_level("DEBUG"):
        Converter(batch_size=10).convert(
            str(larger_csv),
            str(out),
            options={
                "engine": "python",
                "threads": 2,
                "progress": False,
                "summary": False,
                "batch_size": 10,
            },
        )
    assert "Parallel convert failed" not in caplog.text
    assert "parallel Python path" in caplog.text
    assert len(_read_jsonl(out)) == 50
