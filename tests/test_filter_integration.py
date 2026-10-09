"""Integration tests for filter functionality in validator and selector commands."""

import os

import pytest

from undatum.cmds.selector import Selector
from undatum.cmds.validator import Validator

# Contents of the sample_csv_file / sample_jsonl_file fixtures (tests/conftest.py).
SAMPLE_CSV = (
    "name,age,city,active\n"
    "Alice,30,New York,true\n"
    "Bob,25,London,false\n"
    "Charlie,35,Paris,true\n"
    "Diana,28,Berlin,false\n"
)
SAMPLE_JSONL = (
    '{"name": "Alice", "age": 30, "city": "New York", "active": true}\n'
    '{"name": "Bob", "age": 25, "city": "London", "active": false}\n'
    '{"name": "Charlie", "age": 35, "city": "Paris", "active": true}\n'
    '{"name": "Diana", "age": 28, "city": "Berlin", "active": false}\n'
)


class TestValidatorFilter:
    """Test validator command with filter expressions."""

    def test_validator_with_filter_csv(self, sample_csv_file, tmp_path):
        """Test validator with filter on CSV file."""
        validator = Validator()
        output_file = str(tmp_path / "output.csv")

        options = {
            "format_in": "csv",
            "fields": "age",
            "rule": "integer",
            "filter": "age >= 30",  # Filter for age >= 30
            "output": output_file,
            "mode": "all",
            "zipfile": False,
        }

        # Should not raise exception
        validator.validate(sample_csv_file, options)

        # Check that output file was created
        assert os.path.exists(output_file)

    def test_validator_with_filter_jsonl(self, sample_jsonl_file, tmp_path):
        """Test validator with filter on JSONL file."""
        validator = Validator()
        output_file = str(tmp_path / "output.csv")

        options = {
            "format_in": "jsonl",
            "fields": "age",
            "rule": "integer",
            "filter": "age >= 30",  # Filter for age >= 30
            "output": output_file,
            "mode": "all",
            "zipfile": False,
        }

        # Should not raise exception
        validator.validate(sample_jsonl_file, options)

        # Check that output file was created
        assert os.path.exists(output_file)

    def test_validator_with_filter_none(self, sample_csv_file, tmp_path):
        """Test validator with no filter (None)."""
        validator = Validator()
        output_file = str(tmp_path / "output.csv")

        options = {
            "format_in": "csv",
            "fields": "age",
            "rule": "integer",
            "filter": None,  # No filter
            "output": output_file,
            "mode": "all",
            "zipfile": False,
        }

        # Should not raise exception
        validator.validate(sample_csv_file, options)

        # Check that output file was created
        assert os.path.exists(output_file)


class TestSelectorFilter:
    """Test selector command with filter expressions."""

    def test_selector_select_with_filter(self, sample_jsonl_file, tmp_path):
        """Test selector select method with filter."""
        selector = Selector()
        output_file = str(tmp_path / "output.jsonl")

        options = {
            "format_in": "jsonl",
            "fields": "name,age",
            "filter": "age >= 30",  # Filter for age >= 30
            "output": output_file,
        }

        # Should not raise exception
        selector.select(sample_jsonl_file, options)

        # Check that output file was created (if output specified)
        if output_file:
            assert os.path.exists(output_file)

    def test_selector_frequency_with_filter(self, sample_jsonl_file, tmp_path):
        """Test selector frequency method with filter."""
        selector = Selector()
        output_file = str(tmp_path / "output.csv")

        options = {
            "format_in": "jsonl",
            "fields": "city",
            "filter": "age >= 30",  # Filter for age >= 30
            "output": output_file,
            "engine": "iterable",
        }

        # Should not raise exception
        selector.frequency(sample_jsonl_file, options)

        # Check that output file was created
        assert os.path.exists(output_file)

    def test_selector_split_with_filter_csv(self, sample_csv_file, tmp_path):
        """Test selector split method with filter on CSV."""
        selector = Selector()

        options = {
            "format_in": "csv",
            "fields": None,
            "chunksize": 2,
            "filter": "age >= 30",  # Filter for age >= 30
            "zipfile": False,
            "gzipfile": False,
            "dirname": str(tmp_path),
        }

        # Should not raise exception
        # Note: This will create output files in tmp_path
        selector.split(sample_csv_file, options)

    def test_selector_split_with_filter_jsonl(self, sample_jsonl_file, tmp_path):
        """Test selector split method with filter on JSONL."""
        selector = Selector()

        options = {
            "format_in": "jsonl",
            "fields": None,
            "chunksize": 2,
            "filter": "age >= 30",  # Filter for age >= 30
            "zipfile": False,
            "gzipfile": False,
            "dirname": str(tmp_path),
        }

        # Should not raise exception
        selector.split(sample_jsonl_file, options)

    def test_selector_with_filter_none(self, sample_jsonl_file, tmp_path):
        """Test selector with no filter (None)."""
        selector = Selector()
        output_file = str(tmp_path / "output.jsonl")

        options = {
            "format_in": "jsonl",
            "fields": "name,age",
            "filter": None,  # No filter
            "output": output_file,
        }

        # Should not raise exception
        selector.select(sample_jsonl_file, options)


class TestDuckDBFilterPushdown:
    """DuckDB frequency/uniq should honor filters via SQL when translatable."""

    def test_frequency_duckdb_with_filter(self, sample_jsonl_file, tmp_path):
        import csv

        pytest.importorskip("duckdb")
        output_file = str(tmp_path / "freq_duckdb.csv")
        Selector().frequency(
            sample_jsonl_file,
            {
                "format_in": "jsonl",
                "fields": "city",
                "filter": "age >= 30",
                "output": output_file,
                "engine": "duckdb",
            },
        )
        rows = list(csv.reader(open(output_file, encoding="utf8")))
        body = {row[0]: int(row[1]) for row in rows[1:]}
        assert body == {"New York": 1, "Paris": 1}

    def test_uniq_duckdb_with_filter(self, sample_jsonl_file, tmp_path):
        import csv

        pytest.importorskip("duckdb")
        output_file = str(tmp_path / "uniq_duckdb.csv")
        Selector().uniq(
            sample_jsonl_file,
            {
                "format_in": "jsonl",
                "fields": "city",
                "filter": "age >= 30",
                "output": output_file,
                "engine": "duckdb",
            },
        )
        rows = list(csv.reader(open(output_file, encoding="utf8")))
        values = {row[0] for row in rows[1:]}
        assert values == {"New York", "Paris"}

    def test_frequency_untranslatable_filter_errors(self, sample_jsonl_file, tmp_path):
        """IN/LIKE/match are rejected; use undatum sql instead of in-process fallback."""
        with pytest.raises(ValueError, match="undatum sql"):
            Selector().frequency(
                sample_jsonl_file,
                {
                    "format_in": "jsonl",
                    "fields": "city",
                    "filter": 'match "New.*" city',
                    "output": str(tmp_path / "freq_fallback.csv"),
                    "engine": "duckdb",
                },
            )
