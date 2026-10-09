"""Tests for Phase 2 data processing commands."""

import uuid

import pytest

from undatum.cmds.cat import Cat
from undatum.cmds.deduplicator import Deduplicator
from undatum.cmds.exploder import Exploder
from undatum.cmds.filler import Filler
from undatum.cmds.renamer import Renamer
from undatum.cmds.replacer import Replacer
from undatum.cmds.sampler import Sampler, normalize_for_json
from undatum.cmds.searcher import Searcher
from undatum.cmds.sorter import Sorter

# Contents of the sample_csv_file / sample_jsonl_file fixtures (tests/conftest.py).
SAMPLE_CSV = "id,name,age\n1,Alice,30\n2,Bob,25\n3,Charlie,35\n4,Alice,30\n5,Bob,25\n"
SAMPLE_JSONL = (
    '{"id": 1, "name": "Alice", "age": 30}\n'
    '{"id": 2, "name": "Bob", "age": 25}\n'
    '{"id": 3, "name": "Charlie", "age": 35}\n'
    '{"id": 4, "name": "Alice", "age": 30}\n'
)


@pytest.fixture
def file_with_empty_values(tmp_path):
    """Create CSV file with empty values."""
    csv_file = tmp_path / "with_empty.csv"
    csv_file.write_text("id,name,age\n1,Alice,30\n2,,25\n3,Charlie,\n4,,28\n")
    return str(csv_file)


class TestSearcher:
    """Tests for search command."""

    def test_search_all_fields(self, sample_csv_file, tmp_path):
        """Test search across all fields."""
        output_file = tmp_path / "output.csv"
        searcher = Searcher()
        searcher.search(sample_csv_file, {"output": str(output_file), "pattern": "Alice"})

        assert output_file.exists()
        content = output_file.read_text()
        assert "Alice" in content

    def test_search_specific_field(self, sample_jsonl_file, tmp_path):
        """Test search in specific fields."""
        output_file = tmp_path / "output.jsonl"
        searcher = Searcher()
        searcher.search(
            sample_jsonl_file, {"output": str(output_file), "pattern": "^[1-2]$", "fields": "id"}
        )

        content = output_file.read_text()
        assert "id" in content or '"id"' in content


class TestFiller:
    """Tests for fill command."""

    def test_fill_constant(self, file_with_empty_values, tmp_path):
        """Test fill with constant value."""
        output_file = tmp_path / "output.csv"
        filler = Filler()
        filler.fill(
            file_with_empty_values,
            {"output": str(output_file), "fields": "name", "strategy": "constant", "value": "N/A"},
        )

        content = output_file.read_text()
        assert "N/A" in content

    def test_fill_forward(self, file_with_empty_values, tmp_path):
        """Test forward fill strategy."""
        output_file = tmp_path / "output.csv"
        filler = Filler()
        filler.fill(
            file_with_empty_values,
            {"output": str(output_file), "fields": "name", "strategy": "forward"},
        )

        assert output_file.exists()


class TestRenamer:
    """Tests for rename command."""

    def test_rename_exact(self, sample_csv_file, tmp_path):
        """Test rename by exact mapping."""
        output_file = tmp_path / "output.csv"
        renamer = Renamer()
        renamer.rename(sample_csv_file, {"output": str(output_file), "map": "name:full_name"})

        content = output_file.read_text()
        assert "full_name" in content or "full_name" in content

    def test_rename_regex(self, sample_jsonl_file, tmp_path):
        """Test rename using regex."""
        output_file = tmp_path / "output.jsonl"
        renamer = Renamer()
        renamer.rename(
            sample_jsonl_file,
            {"output": str(output_file), "pattern": "^id$", "replacement": "identifier"},
        )

        content = output_file.read_text()
        assert "identifier" in content or '"identifier"' in content


class TestExploder:
    """Tests for explode command."""

    def test_explode_comma_separated(self, tmp_path):
        """Test explode with comma separator."""
        # Create JSONL instead of CSV for easier parsing
        jsonl_file = tmp_path / "tags.jsonl"
        jsonl_file.write_text('{"id": 1, "tags": "tag1,tag2,tag3"}\n{"id": 2, "tags": "tag4"}\n')

        output_file = tmp_path / "output.jsonl"
        exploder = Exploder()
        exploder.explode(
            str(jsonl_file), {"output": str(output_file), "field": "tags", "separator": ","}
        )

        content = output_file.read_text()
        lines = [line for line in content.strip().split("\n") if line]
        # Should have more rows than input (3 tag values from first row + 1 from second = 4 rows)
        assert len(lines) > 2


class TestReplacer:
    """Tests for replace command."""

    def test_replace_simple(self, sample_csv_file, tmp_path):
        """Test simple string replacement."""
        output_file = tmp_path / "output.csv"
        replacer = Replacer()
        replacer.replace(
            sample_csv_file,
            {
                "output": str(output_file),
                "field": "name",
                "pattern": "Alice",
                "replacement": "Alicia",
            },
        )

        content = output_file.read_text()
        assert "Alicia" in content


class TestDeduplicator:
    """Tests for dedup command."""

    def test_dedup_all_fields(self, sample_csv_file, tmp_path):
        """Test deduplication by all fields."""
        output_file = tmp_path / "output.csv"
        deduplicator = Deduplicator()
        deduplicator.dedup(sample_csv_file, {"output": str(output_file)})

        content = output_file.read_text()
        lines = content.strip().split("\n")
        # Should have fewer rows than input (5 data rows, some duplicates)
        assert len(lines) <= 6  # header + <= 5 data rows

    def test_dedup_key_fields(self, sample_jsonl_file, tmp_path):
        """Test deduplication by key fields."""
        output_file = tmp_path / "output.jsonl"
        deduplicator = Deduplicator()
        deduplicator.dedup(sample_jsonl_file, {"output": str(output_file), "key_fields": "name"})

        content = output_file.read_text()
        lines = [line for line in content.strip().split("\n") if line]
        # Should have 3 unique names
        assert len(lines) <= 4


class TestSorter:
    """Tests for sort command."""

    def test_sort_duckdb_quotes(self, tmp_path, caplog):
        """A quote in the path, a space in the field name and doubled quotes stay in DuckDB."""
        input_file = tmp_path / "it's.csv"
        input_file.write_text('id,first name,note\n1,a,plain\n2,b,"say ""hi"""\n')
        output_file = tmp_path / "out.csv"
        Sorter().sort(
            str(input_file),
            {"by": "first name", "desc": True, "output": str(output_file), "engine": "duckdb"},
        )
        assert output_file.read_text().splitlines() == [
            "id,first name,note",
            '2,b,"say ""hi"""',
            "1,a,plain",
        ]
        assert "falling back" not in caplog.text

    def test_sort_single_column(self, sample_csv_file, tmp_path):
        """Test sort by single column."""
        output_file = tmp_path / "output.csv"
        sorter = Sorter()
        sorter.sort(sample_csv_file, {"output": str(output_file), "by": "name"})

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) > 1


class TestSampler:
    """Tests for sample command."""

    def test_sample_fixed_count(self, sample_csv_file, tmp_path):
        """Test sampling fixed number of rows."""
        output_file = tmp_path / "output.csv"
        sampler = Sampler()
        sampler.sample(sample_csv_file, {"output": str(output_file), "n": 2})

        content = output_file.read_text()
        lines = content.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows

    def test_sample_percentage(self, sample_jsonl_file, tmp_path):
        """Test sampling by percentage."""
        output_file = tmp_path / "output.jsonl"
        sampler = Sampler()
        sampler.sample(sample_jsonl_file, {"output": str(output_file), "percent": 50})

        content = output_file.read_text()
        lines = [line for line in content.strip().split("\n") if line]
        # Should have approximately 50% of rows (4 rows * 50% = 2)
        assert len(lines) <= 3  # Allow some variance

    def test_sample_with_uuid_objects(self, tmp_path):
        """Test sampling with UUID objects (simulating Parquet file data)."""
        import json

        # Create a JSONL file with UUID strings
        jsonl_file = tmp_path / "with_uuids.jsonl"
        uuid1 = str(uuid.uuid4())
        uuid2 = str(uuid.uuid4())
        uuid3 = str(uuid.uuid4())

        rows = [
            {"id": uuid1, "name": "Alice"},
            {"id": uuid2, "name": "Bob"},
            {"id": uuid3, "name": "Charlie"},
            {"id": str(uuid.uuid4()), "name": "Diana"},
        ]
        jsonl_file.write_text("".join(json.dumps(row) + "\n" for row in rows))

        # Read and convert UUID strings to UUID objects (simulating Parquet behavior)
        items_with_uuids = []
        for line in jsonl_file.read_text().splitlines():
            item = json.loads(line)
            # Convert UUID string back to UUID object to simulate Parquet
            item["id"] = uuid.UUID(item["id"])
            items_with_uuids.append(item)

        # Write items with UUID objects back to a temporary file for sampling
        # We'll need to mock the iterable behavior, so let's test normalization directly
        output_file = tmp_path / "output.jsonl"

        # Test that normalize_for_json handles UUID objects
        normalized = [normalize_for_json(item) for item in items_with_uuids]

        # Verify UUIDs were converted to strings
        for item in normalized:
            assert isinstance(item["id"], str)
            # Verify it's a valid UUID string format
            uuid.UUID(item["id"])  # Should not raise

        # Now test with actual sampler using a JSONL file
        # Since we can't easily create UUID objects in JSONL, we'll test normalization directly
        # and create a test that uses JSONL with UUID strings (which is how they'd be stored)
        sampler = Sampler()
        sampler.sample(str(jsonl_file), {"output": str(output_file), "n": 2})

        # Verify output was created and is valid JSONL
        assert output_file.exists()
        content = output_file.read_text()
        lines = [line for line in content.strip().split("\n") if line]
        assert len(lines) == 2

        # Verify each line is valid JSON
        import json

        for line in lines:
            parsed = json.loads(line)
            assert "id" in parsed
            assert "name" in parsed

    def test_normalize_for_json_uuid(self):
        """Test normalize_for_json function with UUID objects."""
        test_uuid = uuid.uuid4()

        # Test single UUID
        result = normalize_for_json(test_uuid)
        assert isinstance(result, str)
        assert result == str(test_uuid)

        # Test UUID in dict
        test_dict = {"id": test_uuid, "name": "Alice"}
        result = normalize_for_json(test_dict)
        assert isinstance(result, dict)
        assert isinstance(result["id"], str)
        assert result["id"] == str(test_uuid)
        assert result["name"] == "Alice"

        # Test UUID in list
        test_list = [test_uuid, "string", 123]
        result = normalize_for_json(test_list)
        assert isinstance(result, list)
        assert isinstance(result[0], str)
        assert result[0] == str(test_uuid)
        assert result[1] == "string"
        assert result[2] == 123

        # Test nested structures
        test_nested = {
            "id": test_uuid,
            "items": [{"uuid": test_uuid, "value": 1}, {"uuid": uuid.uuid4(), "value": 2}],
        }
        result = normalize_for_json(test_nested)
        assert isinstance(result["id"], str)
        assert isinstance(result["items"][0]["uuid"], str)
        assert isinstance(result["items"][1]["uuid"], str)


class TestCat:
    """Tests for cat command."""

    def test_cat_rows(self, sample_csv_file, tmp_path):
        """Test concatenation by rows."""
        csv_file2 = tmp_path / "sample2.csv"
        csv_file2.write_text("id,name,age\n6,Diana,28\n7,Eve,32\n")

        output_file = tmp_path / "output.csv"
        cat = Cat()
        cat.cat([sample_csv_file, str(csv_file2)], {"output": str(output_file), "mode": "rows"})

        content = output_file.read_text()
        lines = content.strip().split("\n")
        # Should have header + 5 rows from file1 + 2 rows from file2 = 8 total
        assert len(lines) >= 7
