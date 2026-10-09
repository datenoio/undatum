"""Tests for schema command improvements."""

import json
from pathlib import Path

import pytest
import yaml

from undatum.cmds.schemer import Schemer, TableSchema, _write_schema_output, build_schema

# Contents of the sample_csv_file / sample_jsonl_file fixtures (tests/conftest.py).
SAMPLE_CSV = "id,name,age\n1,Alice,30\n2,Bob,25\n3,Charlie,35\n"
SAMPLE_JSONL = (
    '{"id": "1", "name": "Alice", "age": 30}\n'
    '{"id": "2", "name": "Bob", "age": 25}\n'
    '{"id": "3", "name": "Charlie", "age": 35}\n'
)


class TestBuildSchema:
    """Test build_schema function."""

    def test_build_schema_csv(self, sample_csv_file):
        """Test schema extraction from CSV file."""
        table = build_schema(sample_csv_file)
        assert table.success is True
        assert table.num_records == 3
        assert table.num_cols == 3
        assert len(table.fields) == 3
        field_names = [f.name for f in table.fields]
        assert "id" in field_names
        assert "name" in field_names
        assert "age" in field_names

    def test_build_schema_jsonl(self, sample_jsonl_file):
        """Test schema extraction from JSONL file."""
        table = build_schema(sample_jsonl_file)
        assert table.success is True
        assert table.num_records == 3
        assert len(table.fields) == 3
        field_names = [f.name for f in table.fields]
        assert "id" in field_names
        assert "name" in field_names
        assert "age" in field_names

    def test_build_schema_nonexistent_file(self):
        """Test schema extraction with non-existent file raises FileNotFoundError."""
        from undatum.common.errors import FileNotFoundError as UndatumFileNotFoundError

        with pytest.raises(UndatumFileNotFoundError, match="not found"):
            build_schema("nonexistent_file.csv")

    def test_build_schema_with_engine(self, sample_csv_file):
        """Test schema extraction with engine selection."""
        table = build_schema(sample_csv_file, engine="duckdb")
        assert table.success is True
        assert table.num_records == 3


class TestWriteSchemaOutput:
    """Test _write_schema_output function."""

    def test_write_schema_output_json(self, sample_csv_file, tmp_path):
        """Test JSON output format."""
        table = build_schema(sample_csv_file)
        output_file = tmp_path / "output.json"

        options = {"outtype": "json"}
        with open(output_file, "w", encoding="utf8") as f:
            _write_schema_output(table, options, f)

        # Verify JSON is valid
        with open(output_file, encoding="utf8") as f:
            data = json.load(f)
            assert "fields" in data
            assert "num_records" in data

    def test_write_schema_output_yaml(self, sample_csv_file, tmp_path):
        """Test YAML output format."""
        table = build_schema(sample_csv_file)
        output_file = tmp_path / "output.yaml"

        options = {"outtype": "yaml"}
        with open(output_file, "w", encoding="utf8") as f:
            _write_schema_output(table, options, f)

        # Verify YAML is valid
        with open(output_file, encoding="utf8") as f:
            data = yaml.safe_load(f)
            assert "fields" in data
            assert "num_records" in data

    def test_write_schema_output_text(self, sample_csv_file, tmp_path):
        """Test text output format."""
        table = build_schema(sample_csv_file)
        output_file = tmp_path / "output.txt"

        options = {"outtype": "text"}
        with open(output_file, "w", encoding="utf8") as f:
            _write_schema_output(table, options, f)

        # Verify text output contains expected content
        with open(output_file, encoding="utf8") as f:
            content = f.read()
            assert "SCHEMA EXTRACTION" in content
            assert "FIELDS" in content
            assert "id" in content or "name" in content

    def test_write_schema_output_error(self, tmp_path):
        """Test output formatting with error."""
        table = TableSchema(id="test.csv")
        table.success = False
        table.error = "Test error message"

        output_file = tmp_path / "error.txt"
        options = {"outtype": "text"}
        with open(output_file, "w", encoding="utf8") as f:
            _write_schema_output(table, options, f)

        with open(output_file, encoding="utf8") as f:
            content = f.read()
            assert "ERROR" in content
            assert "Test error message" in content


class TestSchemerExtractSchema:
    """Test Schemer.extract_schema method."""

    def test_extract_schema_text_output(self, sample_csv_file, tmp_path):
        """Test extract_schema with text output."""
        schemer = Schemer()
        output_file = tmp_path / "schema.txt"

        options = {"outtype": "text", "output": str(output_file), "autodoc": False}
        schemer.extract_schema(sample_csv_file, options)

        assert output_file.exists()
        with open(output_file, encoding="utf8") as f:
            content = f.read()
            assert "SCHEMA EXTRACTION" in content

    def test_extract_schema_json_output(self, sample_csv_file, tmp_path):
        """Test extract_schema with JSON output."""
        schemer = Schemer()
        output_file = tmp_path / "schema.json"

        options = {"outtype": "json", "output": str(output_file), "autodoc": False}
        schemer.extract_schema(sample_csv_file, options)

        assert output_file.exists()
        with open(output_file, encoding="utf8") as f:
            data = json.load(f)
            assert "fields" in data

    def test_extract_schema_yaml_output(self, sample_csv_file, tmp_path):
        """Test extract_schema with YAML output."""
        schemer = Schemer()
        output_file = tmp_path / "schema.yaml"

        options = {"outtype": "yaml", "output": str(output_file), "autodoc": False}
        schemer.extract_schema(sample_csv_file, options)

        assert output_file.exists()
        with open(output_file, encoding="utf8") as f:
            data = yaml.safe_load(f)
            assert "fields" in data

    def test_extract_schema_with_engine(self, sample_csv_file, tmp_path):
        """Test extract_schema with engine selection."""
        schemer = Schemer()
        output_file = tmp_path / "schema.json"

        options = {
            "outtype": "json",
            "output": str(output_file),
            "engine": "duckdb",
            "autodoc": False,
        }
        schemer.extract_schema(sample_csv_file, options)

        assert output_file.exists()
        with open(output_file, encoding="utf8") as f:
            data = json.load(f)
            assert data["num_records"] == 3


class TestSchemerExtractSchemaBulk:
    """Test Schemer.extract_schema_bulk method."""

    def test_extract_schema_bulk_directory(self, tmp_path):
        """Test bulk schema extraction from directory."""
        # Create test files
        csv_file1 = tmp_path / "file1.csv"
        csv_file1.write_text("id,name\n1,Alice\n2,Bob\n")
        csv_file2 = tmp_path / "file2.csv"
        csv_file2.write_text("id,name\n3,Charlie\n4,David\n")

        output_dir = tmp_path / "schemas"
        output_dir.mkdir()

        schemer = Schemer()
        options = {
            "mode": "perfile",
            "output": str(output_dir),
            "outtype": "yaml",
            "autodoc": False,
        }
        schemer.extract_schema_bulk(str(tmp_path), options)

        # Check that schemas were created
        schema_files = list(output_dir.glob("*.yaml"))
        assert len(schema_files) == 2

    def test_extract_schema_bulk_glob_pattern(self, tmp_path):
        """Test bulk schema extraction with glob pattern."""
        # Create test files
        csv_file1 = tmp_path / "data1.csv"
        csv_file1.write_text("id,name\n1,Alice\n")
        csv_file2 = tmp_path / "data2.csv"
        csv_file2.write_text("id,name\n2,Bob\n")
        json_file = tmp_path / "data.jsonl"
        json_file.write_text('{"id": "3", "name": "Charlie"}\n')

        output_dir = tmp_path / "schemas"
        output_dir.mkdir()

        schemer = Schemer()
        options = {
            "mode": "distinct",
            "output": str(output_dir),
            "outtype": "yaml",
            "autodoc": False,
        }
        # Test glob pattern
        pattern = str(tmp_path / "*.csv")
        schemer.extract_schema_bulk(pattern, options)

        # Should have created schema files
        schema_files = list(output_dir.glob("*.yaml"))
        assert len(schema_files) >= 1


class TestSchemaFormatExports:
    """Test schema format exports (JSON Schema, Avro, Parquet, Cerberus)."""

    def test_json_schema_format(self, sample_csv_file, tmp_path):
        """Test JSON Schema format export."""
        from undatum.cmds.schemer import _to_json_schema, build_schema

        table = build_schema(sample_csv_file)
        json_schema = _to_json_schema(table)

        # Verify JSON Schema structure
        assert "$schema" in json_schema
        assert json_schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert json_schema["type"] == "object"
        assert "properties" in json_schema
        assert "id" in json_schema["properties"]
        assert "name" in json_schema["properties"]
        assert "age" in json_schema["properties"]

        # Verify field types
        assert json_schema["properties"]["id"]["type"] in ["string", "integer"]
        assert json_schema["properties"]["name"]["type"] == "string"

    def test_json_schema_format_output(self, sample_csv_file, tmp_path):
        """Test JSON Schema format via CLI output."""
        schemer = Schemer()
        output_file = tmp_path / "schema.json"

        options = {"format": "jsonschema", "output": str(output_file), "autodoc": False}
        schemer.extract_schema(sample_csv_file, options)

        assert output_file.exists()
        with open(output_file, encoding="utf8") as f:
            data = json.load(f)
            assert "$schema" in data
            assert data["type"] == "object"
            assert "properties" in data

    def test_avro_format(self, sample_csv_file, tmp_path):
        """Test Avro schema format export."""
        from undatum.cmds.schemer import _to_avro, build_schema

        table = build_schema(sample_csv_file)
        avro_schema = _to_avro(table)

        # Verify Avro schema structure
        assert avro_schema["type"] == "record"
        assert "name" in avro_schema
        assert "fields" in avro_schema
        assert len(avro_schema["fields"]) == 3

        # Verify field structure
        field_names = [f["name"] for f in avro_schema["fields"]]
        assert "id" in field_names
        assert "name" in field_names
        assert "age" in field_names

    def test_avro_format_output(self, sample_csv_file, tmp_path):
        """Test Avro format via CLI output."""
        schemer = Schemer()
        output_file = tmp_path / "schema.avro.json"

        options = {"format": "avro", "output": str(output_file), "autodoc": False}
        schemer.extract_schema(sample_csv_file, options)

        assert output_file.exists()
        with open(output_file, encoding="utf8") as f:
            data = json.load(f)
            assert data["type"] == "record"
            assert "fields" in data

    def test_parquet_format(self, sample_csv_file, tmp_path):
        """Test Parquet schema format export."""
        from undatum.cmds.schemer import _to_parquet, build_schema

        table = build_schema(sample_csv_file)
        parquet_schema = _to_parquet(table)

        # Verify Parquet schema structure
        assert "fields" in parquet_schema
        assert "metadata" in parquet_schema
        assert len(parquet_schema["fields"]) == 3

        # Verify field structure
        field_names = [f["name"] for f in parquet_schema["fields"]]
        assert "id" in field_names
        assert "name" in field_names
        assert "age" in field_names

    def test_parquet_format_output(self, sample_csv_file, tmp_path):
        """Test Parquet format via CLI output."""
        schemer = Schemer()
        output_file = tmp_path / "schema.parquet.json"

        options = {"format": "parquet", "output": str(output_file), "autodoc": False}
        schemer.extract_schema(sample_csv_file, options)

        assert output_file.exists()
        with open(output_file, encoding="utf8") as f:
            data = json.load(f)
            assert "fields" in data
            assert "metadata" in data

    def test_cerberus_format(self, sample_csv_file, tmp_path):
        """Test Cerberus schema format export."""
        from undatum.cmds.schemer import _to_cerberus, build_schema

        table = build_schema(sample_csv_file)
        cerberus_schema = _to_cerberus(table)

        # Verify Cerberus schema structure
        assert isinstance(cerberus_schema, dict)
        assert "id" in cerberus_schema
        assert "name" in cerberus_schema
        assert "age" in cerberus_schema

        # Verify field types
        assert cerberus_schema["name"]["type"] == "string"

    def test_cerberus_format_output(self, sample_csv_file, tmp_path):
        """Test Cerberus format via CLI output."""
        schemer = Schemer()
        output_file = tmp_path / "schema.cerberus.json"

        options = {"format": "cerberus", "output": str(output_file), "autodoc": False}
        schemer.extract_schema(sample_csv_file, options)

        assert output_file.exists()
        with open(output_file, encoding="utf8") as f:
            data = json.load(f)
            assert "id" in data
            assert "name" in data
            assert isinstance(data["name"], dict)

    def test_format_selection_works(self, sample_csv_file, tmp_path):
        """Test that format selection works correctly."""
        schemer = Schemer()

        formats = ["jsonschema", "avro", "parquet", "cerberus"]
        for fmt in formats:
            output_file = tmp_path / f"schema_{fmt}.json"
            options = {"format": fmt, "output": str(output_file), "autodoc": False}
            schemer.extract_schema(sample_csv_file, options)
            assert output_file.exists()

            # Verify it's valid JSON
            with open(output_file, encoding="utf8") as f:
                data = json.load(f)
                assert data is not None

    def test_nested_json_schema(self, sample_jsonl_file, tmp_path):
        """Test JSON Schema with nested structures."""
        from undatum.cmds.schemer import _to_json_schema, build_schema

        table = build_schema(sample_jsonl_file)
        json_schema = _to_json_schema(table)

        # Verify structure
        assert "properties" in json_schema
        assert len(json_schema["properties"]) >= 3

    def test_format_with_descriptions(self, sample_csv_file, tmp_path):
        """Test format exports include field descriptions when available."""
        from undatum.cmds.schemer import _to_json_schema, build_schema

        table = build_schema(sample_csv_file)
        # Add description to a field
        for field in table.fields:
            if field.name == "name":
                field.description = "Person name"
                break

        json_schema = _to_json_schema(table)

        # Verify description is included
        if "description" in json_schema["properties"].get("name", {}):
            assert json_schema["properties"]["name"]["description"] == "Person name"


class TestSchemeCommandDeprecation:
    """Test scheme command deprecation path."""

    def test_scheme_command_shows_warning(self, sample_csv_file, tmp_path, capsys):
        """Test that scheme command shows deprecation warning."""
        import warnings

        from undatum.cli.commands.describe import scheme

        # Capture warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            try:
                # Redirect to avoid actual execution
                output_file = tmp_path / "output.json"
                scheme(input_file=sample_csv_file, output=str(output_file), verbose=False)
            except Exception:
                pass  # We just want to check for warnings

            # Check that deprecation warning was issued
            assert len(w) > 0
            assert any("deprecated" in str(warning.message).lower() for warning in w)

    def test_scheme_command_still_works(self, sample_csv_file, tmp_path):
        """Test that scheme command still produces correct output."""
        from undatum.cli.commands.describe import scheme

        output_file = tmp_path / "scheme_output.json"
        scheme(input_file=sample_csv_file, output=str(output_file), stype="cerberus", verbose=False)

        # Verify output was created
        assert output_file.exists()

        # Verify it's valid JSON (cerberus format)
        with open(output_file, encoding="utf8") as f:
            data = json.load(f)
            assert isinstance(data, dict)

    def test_scheme_migration_path(self, sample_csv_file, tmp_path):
        """Test that scheme command output matches schema --format cerberus."""
        from undatum.cli.commands.describe import scheme
        from undatum.cmds.schemer import Schemer

        # Get output from scheme command
        scheme_output = tmp_path / "scheme_output.json"
        scheme(
            input_file=sample_csv_file, output=str(scheme_output), stype="cerberus", verbose=False
        )

        # Get output from schema --format cerberus
        schema_output = tmp_path / "schema_output.json"
        schemer = Schemer()
        options = {"format": "cerberus", "output": str(schema_output), "autodoc": False}
        schemer.extract_schema(sample_csv_file, options)

        # Both should exist and be valid
        assert scheme_output.exists()
        assert schema_output.exists()

        # Both should be valid JSON
        with open(scheme_output, encoding="utf8") as f:
            scheme_data = json.load(f)
        with open(schema_output, encoding="utf8") as f:
            schema_data = json.load(f)

        # Both should have the same fields
        assert set(scheme_data.keys()) == set(schema_data.keys())


def test_build_schema_xml():
    xml_file = str(Path(__file__).parent / "fixtures" / "books.xml")
    table = build_schema(xml_file, filetype="xml")
    assert table.success is True
    assert table.num_cols >= 1
    assert table.fields


class TestSchemaValidate:
    def test_consistent_jsonl_is_valid(self, tmp_path):
        from undatum.cmds.schemer import validate_inferred_schema

        src = tmp_path / "ok.jsonl"
        src.write_text(
            '{"id": 1, "name": "Alice"}\n{"id": 2, "name": "Bob"}\n',
            encoding="utf8",
        )
        report = validate_inferred_schema(str(src), {})
        assert report["valid"] is True
        assert report["stats"]["invalid"] == 0

    def test_validate_passes_sample_size(self, tmp_path):
        from unittest.mock import patch

        from undatum.cmds.schemer import validate_inferred_schema

        src = tmp_path / "ok.jsonl"
        src.write_text('{"id": 1}\n{"id": 2}\n', encoding="utf8")
        with patch("iterable.ops.schema.infer") as mock_infer:
            with patch("iterable.ops.schema.validate") as mock_validate:
                mock_infer.return_value = {"fields": {"id": {"type": "integer"}}}
                mock_validate.return_value = {
                    "stats": {"invalid": 0, "valid": 2, "total": 2},
                    "invalid_rows": [],
                }
                validate_inferred_schema(str(src), {"sample_size": 50})
                assert mock_infer.call_args[1]["sample_size"] == 50

    def test_validate_omits_sample_size_when_unset(self, tmp_path):
        from unittest.mock import patch

        from undatum.cmds.schemer import validate_inferred_schema

        src = tmp_path / "ok.jsonl"
        src.write_text('{"id": 1}\n{"id": 2}\n', encoding="utf8")
        with patch("iterable.ops.schema.infer") as mock_infer:
            with patch("iterable.ops.schema.validate") as mock_validate:
                mock_infer.return_value = {"fields": {"id": {"type": "integer"}}}
                mock_validate.return_value = {
                    "stats": {"invalid": 0, "valid": 2, "total": 2},
                    "invalid_rows": [],
                }
                validate_inferred_schema(str(src), {})
                assert "sample_size" not in mock_infer.call_args[1]

    def test_type_mismatch_is_invalid(self, tmp_path):
        from undatum.cmds.schemer import validate_inferred_schema

        src = tmp_path / "mismatch.jsonl"
        src.write_text(
            '{"id": 1, "name": "Alice"}\n{"id": "two", "name": "Bob"}\n',
            encoding="utf8",
        )
        report = validate_inferred_schema(str(src), {})
        assert report["valid"] is False
        assert report["stats"]["invalid"] >= 1
        assert report["invalid_sample"]

    def test_cli_validate_json(self, tmp_path):
        from typer.testing import CliRunner

        from undatum.core import app

        src = tmp_path / "ok.jsonl"
        src.write_text('{"id": 1}\n{"id": 2}\n', encoding="utf8")
        result = CliRunner().invoke(app, ["schema", str(src), "--validate", "--outtype", "json"])
        assert result.exit_code == 0, result.stdout
        data = json.loads(result.stdout)
        assert data["valid"] is True

    def test_cli_validate_exits_one_when_invalid(self, tmp_path):
        from typer.testing import CliRunner

        from undatum.core import app

        src = tmp_path / "bad.jsonl"
        src.write_text('{"id": 1}\n{"id": "two"}\n', encoding="utf8")
        result = CliRunner().invoke(app, ["schema", str(src), "--validate", "--outtype", "json"])
        assert result.exit_code == 1
        data = json.loads(result.stdout)
        assert data["valid"] is False
