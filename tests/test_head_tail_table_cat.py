"""Tests for head, tail, table, and cat commands."""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from undatum.cmds.cat import Cat
from undatum.cmds.head import Head
from undatum.cmds.table import TableFormatter
from undatum.cmds.tail import Tail


class TestHead:
    """Test Head class."""

    def test_init(self):
        """Test Head initialization."""
        head = Head()
        assert head is not None

    @pytest.mark.parametrize("engine", ["python", "duckdb"])
    def test_head_basic(self, tmp_path, engine):
        """The first n records are written, on both engines."""
        source = tmp_path / "in.jsonl"
        source.write_text("".join(f'{{"id": {i}}}\n' for i in range(1, 6)), encoding="utf8")
        out = tmp_path / "out.jsonl"
        Head().head(str(source), {"n": 3, "output": str(out), "engine": engine})
        assert out.read_text().splitlines() == ['{"id": 1}', '{"id": 2}', '{"id": 3}']


class TestTail:
    """Test Tail class."""

    def test_tail_basic(self, tmp_path):
        source = tmp_path / "in.jsonl"
        source.write_text("".join(f'{{"id": {i}}}\n' for i in range(1, 6)), encoding="utf8")
        out = tmp_path / "out.jsonl"
        Tail().tail(str(source), {"n": 3, "output": str(out)})
        assert out.read_text().splitlines() == ['{"id": 3}', '{"id": 4}', '{"id": 5}']


class TestTableFormatter:
    """Test TableFormatter class."""

    def test_init(self):
        """Test TableFormatter initialization."""
        formatter = TableFormatter()
        assert formatter.console is not None

    @patch("undatum.cmds.table.open_iterable")
    def test_table_basic(self, mock_open_iterable):
        """Test basic table formatting."""
        formatter = TableFormatter()

        mock_iterable = MagicMock()
        mock_iterable.__iter__ = MagicMock(
            return_value=iter([{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}])
        )
        mock_open_iterable.return_value = mock_iterable

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"name": "Alice", "age": 30}\n{"name": "Bob", "age": 25}\n')
            temp_path = f.name

        try:
            options = {"limit": 10}
            # Table formatter prints to console, so we just verify it doesn't raise
            formatter.table(temp_path, options)
            mock_open_iterable.assert_called()
        finally:
            os.unlink(temp_path)

    @patch("undatum.cmds.table.open_iterable")
    def test_table_with_fields(self, mock_open_iterable):
        """Test table with field selection."""
        formatter = TableFormatter()

        mock_iterable = MagicMock()
        mock_iterable.__iter__ = MagicMock(
            return_value=iter([{"name": "Alice", "age": 30, "city": "NYC"}])
        )
        mock_open_iterable.return_value = mock_iterable

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"name": "Alice", "age": 30, "city": "NYC"}\n')
            temp_path = f.name

        try:
            options = {"fields": "name,age", "limit": 10}
            with patch("builtins.print"):
                formatter.table(temp_path, options)
        finally:
            os.unlink(temp_path)


class TestCat:
    """Test Cat class."""

    def _files(self, tmp_path):
        first = tmp_path / "a.csv"
        first.write_text("id,name\n1,Alice\n2,Bob\n", encoding="utf8")
        second = tmp_path / "b.csv"
        second.write_text("id,city\n3,Rome\n", encoding="utf8")
        return str(first), str(second)

    def test_cat_rows_mode(self, tmp_path):
        """Rows are appended; the header is the union of the files' fields."""
        out = tmp_path / "out.csv"
        Cat().cat(list(self._files(tmp_path)), {"mode": "rows", "output": str(out)})
        assert out.read_text().splitlines() == ["id,name,city", "1,Alice,", "2,Bob,", "3,,Rome"]

    def test_cat_columns_mode(self, tmp_path):
        """Record i of every file is merged; the shorter file just ends."""
        out = tmp_path / "out.jsonl"
        Cat().cat(list(self._files(tmp_path)), {"mode": "columns", "output": str(out)})
        rows = [json.loads(line) for line in out.read_text().splitlines()]
        assert rows == [
            {"id": "3", "name": "Alice", "city": "Rome"},
            {"id": "2", "name": "Bob"},
        ]
