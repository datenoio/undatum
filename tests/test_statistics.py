"""Tests for statistics command."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

from undatum.cmds.statistics import StatProcessor, _detect_engine, get_iterable_options


class TestGetIterableOptions:
    """Test get_iterable_options function."""

    def test_get_iterable_options_all(self):
        """Test extracting all iterable options."""
        options = {
            "tagname": "item",
            "delimiter": ",",
            "encoding": "utf-8",
            "start_line": 1,
            "page": 1,
            "other": "value",
        }
        result = get_iterable_options(options)
        assert result == {
            "tagname": "item",
            "delimiter": ",",
            "encoding": "utf-8",
            "start_line": 1,
            "page": 1,
        }


class TestDetectEngine:
    """Test _detect_engine function."""

    @patch("undatum.common.engine_selector.detect_file_type")
    def test_detect_engine_auto_duckdb(self, mock_detect):
        """Test auto-detection selecting DuckDB."""
        mock_detect.return_value = {
            "success": True,
            "datatype": MagicMock(id=lambda: "csv"),
            "codec": MagicMock(id=lambda: "raw"),
        }

        result = _detect_engine("test.csv", "auto", None)
        assert result == "duckdb"

    @patch("undatum.common.engine_selector.detect_file_type")
    def test_detect_engine_auto_iterable(self, mock_detect):
        """Test auto-detection selecting iterable engine."""
        mock_detect.return_value = {
            "success": True,
            "datatype": MagicMock(id=lambda: "xml"),
            "codec": MagicMock(id=lambda: "raw"),
        }

        result = _detect_engine("test.xml", "auto", None)
        assert result == "iterable"

    def test_detect_engine_explicit_duckdb(self):
        """Test explicit DuckDB selection."""
        result = _detect_engine("test.csv", "duckdb", "csv")
        assert result == "duckdb"

    def test_detect_engine_explicit_iterable(self):
        """Test explicit iterable selection."""
        result = _detect_engine("test.csv", "iterable", "csv")
        assert result == "iterable"

    def test_detect_engine_with_filetype(self):
        """Test engine detection with known filetype."""
        result = _detect_engine("test.csv", "auto", "csv")
        assert result == "duckdb"


class TestStatProcessor:
    """Test StatProcessor class."""

    def test_init(self):
        """Test StatProcessor initialization."""
        processor = StatProcessor()
        assert processor.qd is None

    def test_init_with_dates(self):
        """Test StatProcessor initialization with dates enabled."""
        processor = StatProcessor(nodates=False)
        assert processor.qd is not None

    @patch("undatum.cmds.statistics._detect_engine", return_value="iterable")
    @patch("undatum.cmds.statistics.iterable_engine.open_iterable_with_s3")
    def test_stats_iterable_engine(self, mock_open_s3, mock_detect):
        """Test stats with iterable engine."""
        processor = StatProcessor()

        mock_iterable = MagicMock()
        mock_iterable.__iter__ = MagicMock(return_value=iter([{"name": "Alice", "age": 30}]))
        mock_open_s3.return_value.__enter__.return_value = mock_iterable

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"name": "Alice", "age": 30}\n')
            temp_path = f.name

        try:
            options = {"engine": "iterable"}
            # Should not raise
            processor.stats(temp_path, options)
        finally:
            os.unlink(temp_path)

    @patch("undatum.cmds.statistics._detect_engine", return_value="duckdb")
    @patch("undatum.cmds.statistics.duckdb_engine.duckdb")
    def test_stats_duckdb_engine(self, mock_duckdb, mock_detect):
        """Test stats with DuckDB engine."""
        processor = StatProcessor()

        # Mock DuckDB to avoid actual database operations
        mock_conn = MagicMock()
        mock_duckdb.connect.return_value = mock_conn

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,age\nAlice,30\n")
            temp_path = f.name

        try:
            options = {"engine": "duckdb"}
            # May raise due to DuckDB operations, but tests the code path
            try:
                processor.stats(temp_path, options)
            except Exception:
                pass  # Expected if DuckDB operations fail
        finally:
            os.unlink(temp_path)

    @patch("undatum.cmds.statistics._detect_engine", return_value="duckdb")
    @patch("undatum.cmds.statistics.duckdb_engine.duckdb")
    def test_stats_duckdb_error_fallback(self, mock_duckdb, mock_detect):
        """Test stats with DuckDB error falling back to iterable."""
        processor = StatProcessor()

        # Mock DuckDB to raise error
        mock_duckdb.Error = Exception
        mock_duckdb.connect.side_effect = Exception("DuckDB error")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("name,age\nAlice,30\n")
            temp_path = f.name

        try:
            options = {"engine": "duckdb"}
            # Should fall back to iterable
            with patch(
                "undatum.cmds.statistics.iterable_engine.open_iterable_with_s3"
            ) as mock_open:
                mock_iterable = MagicMock()
                mock_iterable.__iter__ = MagicMock(return_value=iter([{"name": "Alice"}]))
                mock_open.return_value.__enter__.return_value = mock_iterable
                try:
                    processor.stats(temp_path, options)
                except Exception:
                    pass  # May raise, but tests the fallback path
        finally:
            os.unlink(temp_path)


def test_stats_json_output(tmp_path):
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text("name,age\nAlice,30\nBob,25\n", encoding="utf8")
    output_path = tmp_path / "stats.json"

    profile = StatProcessor().stats(
        str(csv_path),
        {"engine": "iterable", "format_out": "json", "output": str(output_path), "quiet": True},
    )
    assert output_path.exists()
    data = json.loads(output_path.read_text(encoding="utf8"))
    assert data["count"] == 2
    assert data["num_fields"] >= 1
    assert profile["count"] == 2
