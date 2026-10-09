"""Tests for renamer command."""

import json
import os
import tempfile

import pytest

from undatum.cmds.renamer import Renamer
from undatum.common.command_utils import get_iterable_options


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


class TestRenamer:
    """Test Renamer class."""

    def test_init(self):
        """Test Renamer initialization."""
        renamer = Renamer()
        assert renamer is not None

    @pytest.mark.parametrize("engine", ["python", "duckdb"])
    def test_rename_with_mapping(self, tmp_path, engine):
        """Mapped fields are renamed, others kept, on both engines."""
        source = tmp_path / "in.jsonl"
        source.write_text('{"old_name": "Alice", "age": 30}\n', encoding="utf8")
        out = tmp_path / "out.jsonl"
        Renamer().rename(
            str(source), {"map": "old_name:new_name", "output": str(out), "engine": engine}
        )
        assert json.loads(out.read_text()) == {"new_name": "Alice", "age": 30}

    @pytest.mark.parametrize("engine", ["python", "duckdb"])
    def test_rename_with_regex_pattern(self, tmp_path, engine):
        """A regex renames every matching field name."""
        source = tmp_path / "in.csv"
        source.write_text("old_a,old_b,c\n1,2,3\n", encoding="utf8")
        out = tmp_path / "out.csv"
        Renamer().rename(
            str(source),
            {"pattern": "^old_", "replacement": "new_", "output": str(out), "engine": engine},
        )
        assert out.read_text().splitlines() == ["new_a,new_b,c", "1,2,3"]

    def test_rename_invalid_regex(self):
        """Test rename with invalid regex pattern."""
        renamer = Renamer()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"field": "value"}\n')
            temp_path = f.name

        try:
            options = {"pattern": "[invalid", "replacement": ""}
            from undatum.common.errors import ValidationError

            with pytest.raises(ValidationError, match="Invalid regex pattern"):
                renamer.rename(temp_path, options)
        finally:
            os.unlink(temp_path)
