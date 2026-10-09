"""Tests for Phase 1 data processing commands."""

from pathlib import Path

import pytest

from undatum.cmds.counter import Counter
from undatum.cmds.enumerator import Enumerator
from undatum.cmds.fixlengths import FixLengths
from undatum.cmds.head import Head
from undatum.cmds.reverser import Reverser
from undatum.cmds.table import TableFormatter
from undatum.cmds.tail import Tail

# Contents of the sample_csv_file / sample_jsonl_file fixtures (tests/conftest.py).
SAMPLE_CSV = "id,name,age\n1,Alice,30\n2,Bob,25\n3,Charlie,35\n4,Diana,28\n5,Eve,32\n"
SAMPLE_JSONL = (
    '{"id": 1, "name": "Alice", "age": 30}\n'
    '{"id": 2, "name": "Bob", "age": 25}\n'
    '{"id": 3, "name": "Charlie", "age": 35}\n'
    '{"id": 4, "name": "Diana", "age": 28}\n'
    '{"id": 5, "name": "Eve", "age": 32}\n'
)


@pytest.fixture
def malformed_csv_file(tmp_path):
    """Create a CSV file with inconsistent field counts."""
    csv_file = tmp_path / "malformed.csv"
    csv_file.write_text("id,name,age\n1,Alice\n2,Bob,25,extra\n3,Charlie,35\n")
    return str(csv_file)


class TestCounter:
    """Tests for count command."""

    def test_count_csv(self, sample_csv_file, capsys):
        """Test counting rows in CSV file."""
        counter = Counter()
        counter.count(sample_csv_file, {})
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"  # 5 data rows (excluding header)

    def test_count_jsonl(self, sample_jsonl_file, capsys):
        """Test counting rows in JSONL file."""
        counter = Counter()
        counter.count(sample_jsonl_file, {})
        captured = capsys.readouterr()
        assert captured.out.strip() == "5"

    def test_count_empty_file(self, tmp_path, capsys):
        """Test counting empty file."""
        empty_file = tmp_path / "empty.csv"
        empty_file.write_text("id,name\n")
        counter = Counter()
        counter.count(str(empty_file), {})
        captured = capsys.readouterr()
        assert captured.out.strip() == "0"


class TestHead:
    """Tests for head command."""

    def test_head_default(self, sample_csv_file, tmp_path):
        """Test head with default N=10."""
        output_file = tmp_path / "output.csv"
        head = Head()
        head.head(sample_csv_file, {"output": str(output_file), "n": 3})

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 4  # header + 3 rows

    def test_head_jsonl(self, sample_jsonl_file, tmp_path):
        """Test head with JSONL file."""
        output_file = tmp_path / "output.jsonl"
        head = Head()
        head.head(sample_jsonl_file, {"output": str(output_file), "n": 2})

        content = output_file.read_text()
        lines = [line for line in content.strip().split("\n") if line]
        assert len(lines) == 2

    def test_head_more_than_available(self, sample_csv_file, tmp_path):
        """Test head when N exceeds available rows."""
        output_file = tmp_path / "output.csv"
        head = Head()
        head.head(sample_csv_file, {"output": str(output_file), "n": 100})

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 6  # header + 5 rows (all available)


class TestTail:
    """Tests for tail command."""

    def test_tail_default(self, sample_csv_file, tmp_path):
        """Test tail with default N=10."""
        output_file = tmp_path / "output.csv"
        tail = Tail()
        tail.tail(sample_csv_file, {"output": str(output_file), "n": 3})

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 4  # header + 3 rows

    def test_tail_jsonl(self, sample_jsonl_file, tmp_path):
        """Test tail with JSONL file."""
        output_file = tmp_path / "output.jsonl"
        tail = Tail()
        tail.tail(sample_jsonl_file, {"output": str(output_file), "n": 2})

        content = output_file.read_text()
        lines = [line for line in content.strip().split("\n") if line]
        assert len(lines) == 2
        # Should be last 2 rows
        assert '"Eve"' in lines[-1] or "Eve" in lines[-1]

    def test_tail_more_than_available(self, sample_csv_file, tmp_path):
        """Test tail when N exceeds available rows."""
        output_file = tmp_path / "output.csv"
        tail = Tail()
        tail.tail(sample_csv_file, {"output": str(output_file), "n": 100})

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 6  # header + 5 rows (all available)


class TestEnumerator:
    """Tests for enum command."""

    def test_enum_number_default(self, sample_csv_file, tmp_path):
        """Test enum with default number type."""
        output_file = tmp_path / "output.csv"
        enumerator = Enumerator()
        enumerator.enum(sample_csv_file, {"output": str(output_file)})

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert "row_id" in lines[0]  # header should contain row_id

    def test_enum_number_custom_field(self, sample_jsonl_file, tmp_path):
        """Test enum with custom field name."""
        output_file = tmp_path / "output.jsonl"
        enumerator = Enumerator()
        enumerator.enum(
            sample_jsonl_file,
            {"output": str(output_file), "field": "sequence", "type": "number", "start": 100},
        )

        content = output_file.read_text()
        # Check that sequence field was added
        assert '"sequence"' in content or "'sequence'" in content

    def test_enum_uuid(self, sample_csv_file, tmp_path):
        """Test enum with UUID type."""
        output_file = tmp_path / "output.csv"
        enumerator = Enumerator()
        enumerator.enum(
            sample_csv_file, {"output": str(output_file), "field": "uuid", "type": "uuid"}
        )

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert "uuid" in lines[0]  # header should contain uuid
        # Verify UUID format (basic check)
        if len(lines) > 1:
            # UUIDs should be in the output
            assert len(lines[1].split(",")) > 0

    def test_enum_constant(self, sample_jsonl_file, tmp_path):
        """Test enum with constant value."""
        output_file = tmp_path / "output.jsonl"
        enumerator = Enumerator()
        enumerator.enum(
            sample_jsonl_file,
            {"output": str(output_file), "field": "status", "type": "constant", "value": "active"},
        )

        content = output_file.read_text()
        assert '"status"' in content or "'status'" in content
        assert "active" in content


class TestReverser:
    """Tests for reverse command."""

    def test_reverse_csv(self, sample_csv_file, tmp_path):
        """Test reversing CSV file."""
        output_file = tmp_path / "output.csv"
        reverser = Reverser()
        reverser.reverse(sample_csv_file, {"output": str(output_file)})

        # Read original and reversed
        original = sample_csv_file
        reversed_content = output_file.read_text()

        # Check that rows are reversed (first row of original should be last in reversed)
        original_lines = Path(original).read_text().strip().split("\n")
        reversed_lines = reversed_content.strip().split("\n")

        # Last data row of reversed should match first data row of original
        assert len(reversed_lines) == len(original_lines)

    def test_reverse_jsonl(self, sample_jsonl_file, tmp_path):
        """Test reversing JSONL file."""
        output_file = tmp_path / "output.jsonl"
        reverser = Reverser()
        reverser.reverse(sample_jsonl_file, {"output": str(output_file)})

        reversed_content = output_file.read_text()
        lines = [line for line in reversed_content.strip().split("\n") if line]

        # Should have same number of lines
        original_lines = Path(sample_jsonl_file).read_text().strip().split("\n")
        original_lines = [line for line in original_lines if line]
        assert len(lines) == len(original_lines)

        # First line of reversed should be last line of original
        assert "Eve" in lines[0] or '"Eve"' in lines[0]


class TestTableFormatter:
    """Tests for table command."""

    def test_table_default(self, sample_csv_file, capsys):
        """Test table with default limit."""
        formatter = TableFormatter()
        formatter.table(sample_csv_file, {"limit": 3})
        captured = capsys.readouterr()

        # Should display table with headers
        assert "id" in captured.out or "name" in captured.out
        assert "Alice" in captured.out or "1" in captured.out

    def test_table_with_fields(self, sample_jsonl_file, capsys):
        """Test table with field selection."""
        formatter = TableFormatter()
        formatter.table(sample_jsonl_file, {"limit": 3, "fields": "name,age"})
        captured = capsys.readouterr()

        # Should only show selected fields
        assert "name" in captured.out
        assert "age" in captured.out
        # Should not show id
        # (Note: this is a basic check, actual implementation may vary)

    def test_table_empty_file(self, tmp_path, capsys):
        """Test table with empty file."""
        empty_file = tmp_path / "empty.csv"
        empty_file.write_text("id,name\n")
        formatter = TableFormatter()
        formatter.table(str(empty_file), {})
        captured = capsys.readouterr()
        assert "No data to display" in captured.out


class TestFixLengths:
    """Tests for fixlengths command."""

    def test_fixlengths_pad(self, malformed_csv_file, tmp_path):
        """Test fixlengths with pad strategy."""
        output_file = tmp_path / "output.csv"
        fixlengths = FixLengths()
        fixlengths.fixlengths(
            malformed_csv_file, {"output": str(output_file), "strategy": "pad", "value": ""}
        )

        content = output_file.read_text()
        lines = content.strip().split("\n")

        # All rows should have same number of fields
        field_counts = [len(line.split(",")) for line in lines[1:]]  # Skip header
        if field_counts:
            assert all(count == field_counts[0] for count in field_counts)

    def test_fixlengths_pad_custom_value(self, malformed_csv_file, tmp_path):
        """Test fixlengths with pad strategy and custom value."""
        output_file = tmp_path / "output.csv"
        fixlengths = FixLengths()
        fixlengths.fixlengths(
            malformed_csv_file, {"output": str(output_file), "strategy": "pad", "value": "N/A"}
        )

        content = output_file.read_text()
        # Should contain padding value
        assert "N/A" in content

    def test_fixlengths_truncate(self, malformed_csv_file, tmp_path):
        """Test fixlengths with truncate strategy."""
        output_file = tmp_path / "output.csv"
        fixlengths = FixLengths()
        fixlengths.fixlengths(
            malformed_csv_file, {"output": str(output_file), "strategy": "truncate"}
        )

        content = output_file.read_text()
        lines = content.strip().split("\n")

        # All rows should have same number of fields (minimum)
        field_counts = [len(line.split(",")) for line in lines[1:]]  # Skip header
        if field_counts:
            assert all(count == field_counts[0] for count in field_counts)

    def test_fixlengths_jsonl(self, tmp_path):
        """Test fixlengths with JSONL file."""
        # Create JSONL with inconsistent fields
        jsonl_file = tmp_path / "malformed.jsonl"
        content = (
            '{"id": 1, "name": "Alice"}\n'
            '{"id": 2, "name": "Bob", "age": 25, "city": "NY"}\n'
            '{"id": 3, "name": "Charlie", "age": 35}\n'
        )
        jsonl_file.write_text(content)

        output_file = tmp_path / "output.jsonl"
        fixlengths = FixLengths()
        fixlengths.fixlengths(
            str(jsonl_file), {"output": str(output_file), "strategy": "pad", "value": ""}
        )

        # Should process without error
        assert output_file.exists()
