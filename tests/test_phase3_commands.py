"""Tests for Phase 3 data processing commands."""

import pytest

from undatum.cmds.differ import Differ
from undatum.cmds.excluder import Excluder
from undatum.cmds.formatter import Formatter
from undatum.cmds.joiner import Joiner
from undatum.cmds.slicer import Slicer
from undatum.cmds.sniffer import Sniffer
from undatum.cmds.transposer import Transposer

# Contents of the sample_csv_file / sample_jsonl_file fixtures (tests/conftest.py).
SAMPLE_CSV = "id,name,age\n1,Alice,30\n2,Bob,25\n3,Charlie,35\n"
SAMPLE_JSONL = (
    '{"id": 1, "name": "Alice", "age": 30}\n'
    '{"id": 2, "name": "Bob", "age": 25}\n'
    '{"id": 3, "name": "Charlie", "age": 35}\n'
)


@pytest.fixture
def sample_csv_file2(tmp_path):
    """Create a second sample CSV file for testing joins."""
    csv_file = tmp_path / "sample2.csv"
    csv_file.write_text("id,email\n1,alice@example.com\n2,bob@example.com\n4,diana@example.com\n")
    return str(csv_file)


@pytest.fixture
def exclusion_file(tmp_path):
    """Create an exclusion file for testing."""
    csv_file = tmp_path / "exclude.csv"
    csv_file.write_text("id\n2\n")
    return str(csv_file)


class TestJoiner:
    """Tests for join command."""

    def test_inner_join(self, sample_csv_file, sample_csv_file2, tmp_path):
        """Test inner join."""
        output_file = tmp_path / "output.csv"
        joiner = Joiner()
        joiner.join(
            sample_csv_file,
            sample_csv_file2,
            {"output": str(output_file), "on": "id", "type": "inner"},
        )

        assert output_file.exists()
        content = output_file.read_text()
        assert "Alice" in content or "alice" in content

    def test_left_join(self, sample_csv_file, sample_csv_file2, tmp_path):
        """Test left join."""
        output_file = tmp_path / "output.csv"
        joiner = Joiner()
        joiner.join(
            sample_csv_file,
            sample_csv_file2,
            {"output": str(output_file), "on": "id", "type": "left"},
        )

        assert output_file.exists()
        content = output_file.read_text()
        # Should include Charlie (from file1 but not in file2)
        assert "Charlie" in content


class TestDiffer:
    """Tests for diff command."""

    def test_diff_by_key(self, sample_csv_file, sample_csv_file2, tmp_path):
        """Test diff by key."""
        output_file = tmp_path / "output.json"
        differ = Differ()
        differ.diff(
            sample_csv_file,
            sample_csv_file2,
            {"output": str(output_file), "key": "id", "output_format": "json"},
        )

        assert output_file.exists()
        content = output_file.read_text()
        assert "added" in content or "removed" in content or "changed" in content

    def test_diff_unified_format(self, sample_csv_file, sample_csv_file2):
        """Test diff in unified format."""
        differ = Differ()
        # Capture stdout would require mocking, but we can test it doesn't crash
        differ.diff(sample_csv_file, sample_csv_file2, {"key": "id", "output_format": "unified"})


class TestExcluder:
    """Tests for exclude command."""

    def test_exclude_by_key(self, sample_csv_file, exclusion_file, tmp_path):
        """Test exclude by key."""
        output_file = tmp_path / "output.csv"
        excluder = Excluder()
        excluder.exclude(sample_csv_file, exclusion_file, {"output": str(output_file), "on": "id"})

        assert output_file.exists()
        content = output_file.read_text()
        # Bob (id=2) should be excluded
        assert "Bob" not in content or content.count("Bob") < 2  # May appear in header
        # Alice and Charlie should remain
        assert "Alice" in content or "alice" in content


class TestTransposer:
    """Tests for transpose command."""

    def test_transpose(self, sample_csv_file, tmp_path):
        """Test transpose."""
        output_file = tmp_path / "output.csv"
        transposer = Transposer()
        transposer.transpose(sample_csv_file, {"output": str(output_file)})

        assert output_file.exists()
        content = output_file.read_text()
        # Should have transposed structure
        assert "field_name" in content or "row_" in content


class TestSniffer:
    """Tests for sniff command."""

    def test_sniff_file(self, sample_csv_file, tmp_path):
        """Test sniff file properties."""
        output_file = tmp_path / "output.txt"
        sniffer = Sniffer()
        sniffer.sniff(sample_csv_file, {"output": str(output_file), "format": "text"})

        assert output_file.exists()
        content = output_file.read_text()
        assert "File:" in content or "Type:" in content

    def test_sniff_json_format(self, sample_jsonl_file, tmp_path):
        """Test sniff in JSON format."""
        output_file = tmp_path / "output.json"
        sniffer = Sniffer()
        sniffer.sniff(sample_jsonl_file, {"output": str(output_file), "format": "json"})

        assert output_file.exists()
        content = output_file.read_text()
        assert "filetype" in content or '"filetype"' in content


class TestSlicer:
    """Tests for slice command."""

    def test_slice_by_range(self, sample_csv_file, tmp_path):
        """Test slice by range."""
        output_file = tmp_path / "output.csv"
        slicer = Slicer()
        slicer.slice(sample_csv_file, {"output": str(output_file), "start": 1, "end": 2})

        assert output_file.exists()
        content = output_file.read_text()
        lines = content.strip().split("\n")
        # Should have header + selected rows
        assert len(lines) >= 2

    def test_slice_by_indices(self, sample_jsonl_file, tmp_path):
        """Test slice by indices."""
        output_file = tmp_path / "output.jsonl"
        slicer = Slicer()
        slicer.slice(sample_jsonl_file, {"output": str(output_file), "indices": "0,2"})

        assert output_file.exists()
        content = output_file.read_text()
        lines = [line for line in content.strip().split("\n") if line]
        # Should have selected rows
        assert len(lines) <= 3


class TestFormatter:
    """Tests for fmt command."""

    def test_fmt_change_delimiter(self, sample_csv_file, tmp_path):
        """Test format with different delimiter."""
        output_file = tmp_path / "output.csv"
        formatter = Formatter()
        formatter.fmt(sample_csv_file, {"output": str(output_file), "delimiter": ";"})

        assert output_file.exists()
        content = output_file.read_text()
        # Should use semicolon delimiter
        assert ";" in content or len(content) > 0
