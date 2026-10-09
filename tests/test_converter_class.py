"""Tests for Converter class."""

import os
import tempfile

from undatum.cmds.converter import Converter, _is_flat, express_analyze_jsonl


class TestExpressAnalyzeJsonl:
    """Test express_analyze_jsonl function."""

    def test_express_analyze_jsonl_flat(self):
        """Test analyzing flat JSONL file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"name": "Alice", "age": 30}\n')
            f.write('{"name": "Bob", "age": 25}\n')
            temp_path = f.name

        try:
            result = express_analyze_jsonl(temp_path, itemlimit=100)
            assert result["isflat"] is True
            assert "name" in result["keys"]
            assert "age" in result["keys"]
        finally:
            os.unlink(temp_path)

    def test_express_analyze_jsonl_nested(self):
        """Test analyzing nested JSONL file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"user": {"name": "Alice", "age": 30}}\n')
            temp_path = f.name

        try:
            result = express_analyze_jsonl(temp_path, itemlimit=100)
            assert result["isflat"] is False
            assert "user" in result["keys"]
        finally:
            os.unlink(temp_path)

    def test_express_analyze_jsonl_with_limit(self):
        """Test analyzing with limit."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            for i in range(200):
                f.write(f'{{"id": {i}}}\n')
            temp_path = f.name

        try:
            result = express_analyze_jsonl(temp_path, itemlimit=10)
            assert "id" in result["keys"]
        finally:
            os.unlink(temp_path)


class TestIsFlat:
    """Test _is_flat function."""

    def test_is_flat_simple_dict(self):
        """Test flat dictionary."""
        item = {"key1": "value1", "key2": "value2"}
        assert _is_flat(item) is True

    def test_is_flat_with_list(self):
        """Test dictionary with list."""
        item = {"key1": "value1", "key2": [1, 2, 3]}
        assert _is_flat(item) is False

    def test_is_flat_with_dict(self):
        """Test dictionary with nested dict."""
        item = {"key1": "value1", "key2": {"nested": "value"}}
        assert _is_flat(item) is False

    def test_is_flat_with_tuple(self):
        """Test dictionary with tuple."""
        item = {"key1": "value1", "key2": (1, 2, 3)}
        assert _is_flat(item) is False


class TestConverter:
    """Test Converter class."""

    def test_init(self):
        """Test Converter initialization."""
        converter = Converter()
        assert converter.batch_size == 50000

    def test_init_custom_batch_size(self):
        """Test Converter initialization with custom batch size."""
        converter = Converter(batch_size=10000)
        assert converter.batch_size == 10000

    def test_convert_returns_result(self, tmp_path):
        """Test convert returns ConversionResult with row metrics."""
        src = tmp_path / "in.csv"
        dst = tmp_path / "out.jsonl"
        src.write_text("a,b\n1,2\n")
        result = Converter().convert(str(src), str(dst), {"progress": False, "summary": False})
        assert result.rows_out == 1
        assert result.elapsed_seconds >= 0
