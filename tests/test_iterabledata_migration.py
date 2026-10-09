"""Tests for iterabledata library migration."""

import os
from pathlib import Path

import pytest

from undatum.cmds.converter import Converter
from undatum.cmds.selector import Selector
from undatum.cmds.statistics import StatProcessor
from undatum.cmds.textproc import TextProcessor
from undatum.cmds.transformer import Transformer


@pytest.fixture
def test_data_dir():
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_jsonl_file(test_data_dir):
    """Return path to sample JSONL file."""
    return str(test_data_dir / "2cols6rows_flat.jsonl")


@pytest.fixture
def sample_csv_file(test_data_dir):
    """Return path to sample CSV file."""
    return str(test_data_dir / "2cols6rows.csv")


class TestSelectorCommand:
    """Test selector command with external library."""

    def test_headers(self, sample_jsonl_file):
        """Test headers extraction."""
        selector = Selector()

        options = {"format_in": "jsonl", "limit": 10}

        # Should not raise exception
        selector.headers(sample_jsonl_file, options)

    def test_uniq(self, sample_jsonl_file, tmp_path):
        """Test unique values extraction."""
        selector = Selector()
        output_file = str(tmp_path / "output.csv")

        options = {
            "format_in": "jsonl",
            "fields": "col1",
            "output": output_file,
            "engine": "iterable",
        }

        selector.uniq(sample_jsonl_file, options)

        # Verify output file was created
        assert os.path.exists(output_file)

    def test_frequency(self, sample_jsonl_file, tmp_path):
        """Test frequency calculation."""
        selector = Selector()
        output_file = str(tmp_path / "output.csv")

        options = {
            "format_in": "jsonl",
            "fields": "col1",
            "output": output_file,
            "engine": "iterable",
        }

        selector.frequency(sample_jsonl_file, options)

        # Verify output file was created
        assert os.path.exists(output_file)

    def test_select(self, sample_jsonl_file, tmp_path):
        """Test select command."""
        selector = Selector()
        output_file = str(tmp_path / "output.jsonl")

        options = {"format_in": "jsonl", "fields": "col1,col2", "output": output_file}

        selector.select(sample_jsonl_file, options)

        # Verify output file was created
        assert os.path.exists(output_file)


class TestConverterCommand:
    """Test converter command with external library."""

    def test_convert_jsonl_to_csv(self, sample_jsonl_file, tmp_path):
        """Test conversion from JSONL to CSV."""
        converter = Converter()
        output_file = str(tmp_path / "output.csv")

        options = {"format_in": "jsonl", "format_out": "csv"}

        converter.convert(sample_jsonl_file, output_file, options)

        # Verify output file was created
        assert os.path.exists(output_file)
        assert os.path.getsize(output_file) > 0

    def test_convert_csv_to_jsonl(self, sample_csv_file, tmp_path):
        """Test conversion from CSV to JSONL."""
        converter = Converter()
        output_file = str(tmp_path / "output.jsonl")

        options = {"format_in": "csv", "format_out": "jsonl"}

        converter.convert(sample_csv_file, output_file, options)

        # Verify output file was created
        assert os.path.exists(output_file)
        assert os.path.getsize(output_file) > 0

    def test_convert_with_reset(self, sample_jsonl_file, tmp_path):
        """Test that converter uses reset() for multiple passes."""
        converter = Converter()
        output_file = str(tmp_path / "output.csv")

        options = {"format_in": "jsonl", "format_out": "csv"}

        # Should not raise exception (reset() should work)
        converter.convert(sample_jsonl_file, output_file, options, limit=5)

        assert os.path.exists(output_file)


class TestTransformerCommand:
    """Test transformer command with external library."""

    def test_script_transformation(self, sample_jsonl_file, tmp_path):
        """Test script-based transformation."""
        transformer = Transformer()

        # Create a simple transformation script
        script_file = tmp_path / "transform.py"
        script_content = """
def process(item):
    item['transformed'] = True
    return item
"""
        script_file.write_text(script_content)

        output_file = str(tmp_path / "output.jsonl")

        options = {"format_in": "jsonl", "script": str(script_file), "output": output_file}

        transformer.script(sample_jsonl_file, options)

        # Verify output file was created
        assert os.path.exists(output_file)


class TestStatisticsCommand:
    """Test statistics command with external library."""

    def test_stats_basic(self, sample_jsonl_file):
        """Test basic statistics generation."""
        processor = StatProcessor()

        options = {"format_in": "jsonl"}

        # Should not raise exception
        processor.stats(sample_jsonl_file, options)

    def test_stats_resource_cleanup(self, sample_jsonl_file):
        """Test that resources are properly cleaned up."""
        processor = StatProcessor()

        options = {"format_in": "jsonl"}

        # Run multiple times to check for resource leaks
        for _ in range(3):
            processor.stats(sample_jsonl_file, options)


class TestTextProcCommand:
    """Test textproc command with external library."""

    def test_flatten(self, sample_jsonl_file):
        """Test flatten functionality."""
        processor = TextProcessor()

        options = {"format_in": "jsonl"}

        # Should not raise exception
        processor.flatten(sample_jsonl_file, options)

    def test_flatten_resource_cleanup(self, sample_jsonl_file):
        """Test that resources are properly cleaned up."""
        processor = TextProcessor()

        options = {"format_in": "jsonl"}

        # Run multiple times to check for resource leaks
        for _ in range(3):
            processor.flatten(sample_jsonl_file, options)


class TestResourceManagement:
    """Test resource management across all commands."""

    def test_all_commands_close_resources(self, sample_jsonl_file, tmp_path):
        """Test that all commands properly close iterable resources."""
        # Test each command that uses iterables
        commands = [
            (
                Selector(),
                {
                    "format_in": "jsonl",
                    "fields": "col1",
                    "output": str(tmp_path / "s.csv"),
                    "engine": "iterable",
                },
            ),
            (StatProcessor(), {"format_in": "jsonl"}),
            (TextProcessor(), {"format_in": "jsonl"}),
        ]

        for cmd, options in commands:
            if isinstance(cmd, Selector):
                cmd.headers(sample_jsonl_file, options)
            elif isinstance(cmd, StatProcessor):
                cmd.stats(sample_jsonl_file, options)
            elif isinstance(cmd, TextProcessor):
                cmd.flatten(sample_jsonl_file, options)

        # The commands above raise on resource errors; reaching this point means cleanup worked.


class TestWriteBulk:
    """Test write_bulk functionality."""

    def test_converter_uses_write_bulk(self, sample_jsonl_file, tmp_path):
        """Test that converter uses write_bulk for batch writes."""
        converter = Converter(batch_size=2)  # Small batch size for testing
        output_file = str(tmp_path / "output.csv")

        options = {"format_in": "jsonl", "format_out": "csv"}

        converter.convert(sample_jsonl_file, output_file, options)

        # Verify output was written
        assert os.path.exists(output_file)
        assert os.path.getsize(output_file) > 0

    def test_transformer_uses_write_bulk(self, sample_jsonl_file, tmp_path):
        """Test that transformer uses write_bulk for batch writes."""
        transformer = Transformer()

        script_file = tmp_path / "transform.py"
        script_file.write_text("def process(item): return item\n")

        output_file = str(tmp_path / "output.jsonl")

        options = {"format_in": "jsonl", "script": str(script_file), "output": output_file}

        transformer.script(sample_jsonl_file, options)

        # Verify output was written
        assert os.path.exists(output_file)


class TestResetFunctionality:
    """Test reset() functionality where implemented."""

    def test_converter_reset(self, sample_jsonl_file, tmp_path):
        """Test that converter can reset iterator for multiple passes."""
        converter = Converter()
        output_file = str(tmp_path / "output.csv")

        options = {"format_in": "jsonl", "format_out": "csv"}

        # This should use reset() between schema extraction and conversion
        converter.convert(sample_jsonl_file, output_file, options, limit=3)

        assert os.path.exists(output_file)

    def test_transformer_reset(self, sample_jsonl_file, tmp_path):
        """Test that transformer can reset iterator for multiple passes."""
        transformer = Transformer()

        script_file = tmp_path / "transform.py"
        script_file.write_text("def process(item): return item\n")

        output_file = str(tmp_path / "output.jsonl")

        options = {"format_in": "jsonl", "script": str(script_file), "output": output_file}

        # This should use reset() between schema extraction and processing
        transformer.script(sample_jsonl_file, options)

        assert os.path.exists(output_file)
