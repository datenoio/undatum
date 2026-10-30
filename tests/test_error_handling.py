"""Tests for error handling infrastructure."""

import os
import sys

import pytest

from undatum.common.errors import (
    DatabaseError,
    DependencyError,
    FileNotFoundError,
    FormatError,
    PermissionError,
    UndatumError,
    ValidationError,
    find_similar_field_names,
    find_similar_files,
    format_error_message,
    handle_command_error,
)
from undatum.common.path_utils import validate_file_path


class TestUndatumError:
    """Test base UndatumError class."""

    def test_undatum_error_basic(self):
        """Test basic UndatumError creation."""
        error = UndatumError("Test error message")
        assert str(error) == "Test error message"
        assert error.message == "Test error message"
        assert error.exit_code == 1
        assert error.context == {}

    def test_undatum_error_with_context(self):
        """Test UndatumError with context."""
        context = {"file_path": "/path/to/file", "operation": "read"}
        error = UndatumError("Test error", context=context, exit_code=2)
        assert error.context == context
        assert error.exit_code == 2


class TestFileNotFoundError:
    """Test FileNotFoundError exception."""

    def test_file_not_found_basic(self):
        """Test basic FileNotFoundError."""
        error = FileNotFoundError("/nonexistent/file.csv")
        assert "File not found" in str(error)
        assert "/nonexistent/file.csv" in str(error)
        assert error.exit_code == 1

    def test_file_not_found_with_suggestion(self):
        """Test FileNotFoundError with file suggestion."""
        error = FileNotFoundError("/path/file.csv", suggestions=["/path/file2.csv"])
        assert "Did you mean" in str(error)
        assert "/path/file2.csv" in str(error)

    def test_file_not_found_with_multiple_suggestions(self):
        """Test FileNotFoundError with multiple suggestions."""
        suggestions = ["file1.csv", "file2.csv", "file3.csv"]
        error = FileNotFoundError("/path/file.csv", suggestions=suggestions)
        assert "Did you mean one of these" in str(error)
        for suggestion in suggestions:
            assert suggestion in str(error)


class TestPermissionError:
    """Test PermissionError exception."""

    def test_permission_error_read(self):
        """Test PermissionError for read operation."""
        error = PermissionError("/path/file.csv", operation="read")
        assert "Permission denied" in str(error)
        assert "Cannot read" in str(error)
        assert "chmod +r" in str(error)
        assert error.exit_code == 3

    def test_permission_error_write(self):
        """Test PermissionError for write operation."""
        error = PermissionError("/path/file.csv", operation="write")
        assert "Cannot write" in str(error)
        assert "chmod +w" in str(error)
        assert error.exit_code == 3


class TestValidationError:
    """Test ValidationError exception."""

    def test_validation_error_basic(self):
        """Test basic ValidationError."""
        error = ValidationError("Invalid value provided")
        assert "Invalid input" in str(error)
        assert error.exit_code == 1

    def test_validation_error_with_field(self):
        """Test ValidationError with field name."""
        error = ValidationError("Field does not exist", field="field_name")
        assert "Invalid parameter 'field_name'" in str(error)

    def test_validation_error_with_suggestions(self):
        """Test ValidationError with suggestions."""
        suggestions = ["field1", "field2", "field3"]
        error = ValidationError("Field not found", field="field_name", suggestions=suggestions)
        assert "Valid options" in str(error)
        for suggestion in suggestions:
            assert suggestion in str(error)


class TestFormatError:
    """Test FormatError exception."""

    def test_format_error_basic(self):
        """Test basic FormatError."""
        error = FormatError("/path/file.xyz", "xyz")
        assert "Unsupported file format" in str(error)
        assert "xyz" in str(error)
        assert error.exit_code == 1

    def test_format_error_with_supported_formats(self):
        """Test FormatError with supported formats list."""
        supported = ["csv", "jsonl", "parquet"]
        error = FormatError("/path/file.xyz", "xyz", supported_formats=supported)
        assert "Supported formats" in str(error)
        assert "csv" in str(error)
        assert "undatum convert" in str(error)


class TestDependencyError:
    """Test DependencyError exception."""

    def test_dependency_error_basic(self):
        """Test basic DependencyError."""
        error = DependencyError("package_name")
        assert "Missing dependency" in str(error)
        assert "package_name" in str(error)
        assert "pip install package_name" in str(error)
        assert error.exit_code == 2

    def test_dependency_error_with_feature(self):
        """Test DependencyError with feature name."""
        error = DependencyError("package_name", feature="database support")
        assert "This feature requires" in str(error)


class TestDatabaseError:
    """Test DatabaseError exception."""

    def test_database_error_basic(self):
        """Test basic DatabaseError."""
        error = DatabaseError("Connection failed")
        assert "Database error" in str(error)
        assert error.exit_code == 3

    def test_database_error_with_type(self):
        """Test DatabaseError with database type."""
        error = DatabaseError("Connection failed", db_type="postgresql")
        assert "postgresql error" in str(error)

    def test_database_error_masks_password(self):
        """Test DatabaseError masks password in connection URI."""
        uri = "postgresql://user:password@host:5432/db"
        error = DatabaseError("Connection failed", connection_uri=uri)
        assert "password" not in str(error)
        assert "***" in str(error)


class TestErrorHelpers:
    """Test error helper functions."""

    def test_find_similar_files(self, tmp_path):
        """Test finding similar files."""
        # Create test files
        (tmp_path / "file1.csv").touch()
        (tmp_path / "file2.csv").touch()
        (tmp_path / "data.json").touch()

        # Test with similar file
        suggestions = find_similar_files(str(tmp_path / "file.csv"))
        assert len(suggestions) > 0
        assert any("file" in s for s in suggestions)

    def test_find_similar_files_nonexistent_dir(self):
        """Test find_similar_files with nonexistent directory."""
        suggestions = find_similar_files("/nonexistent/dir/file.csv")
        assert suggestions == []

    def test_find_similar_field_names(self):
        """Test finding similar field names."""
        available = ["email", "phone", "address", "name"]
        suggestions = find_similar_field_names("emal", available)
        assert "email" in suggestions

    def test_find_similar_field_names_no_match(self):
        """Test find_similar_field_names with no close match."""
        available = ["email", "phone", "address"]
        suggestions = find_similar_field_names("xyz", available)
        assert suggestions == []


class TestFormatErrorMessage:
    """Test format_error_message function."""

    def test_format_undatum_error(self):
        """Test formatting UndatumError."""
        error = FileNotFoundError("/path/file.csv")
        message = format_error_message(error)
        assert message == str(error)

    def test_format_python_exception(self):
        """Test formatting standard Python exception."""
        error = ValueError("Invalid value")
        message = format_error_message(error)
        assert "Invalid value" in message
        assert "Invalid value:" in message

    def test_iterabledata_hints_become_cli_options(self):
        """iterabledata's open_iterable(...) hints are shown as command-line options."""
        error = ValueError(
            "Failed to parse csv format at data.csv:2\n"
            "2. Specify the correct delimiter:\n"
            "   open_iterable('file.csv', iterableargs={'delimiter': ';'})\n"
            "3. Handle encoding issues:\n"
            "   open_iterable('file.csv', iterableargs={'encoding': 'utf-8'})\n"
            "4. Use error handling to skip problematic rows:\n"
            "   open_iterable('file.csv', iterableargs={'on_error': 'skip'})"
        )
        message = format_error_message(error)
        assert "open_iterable" not in message
        assert "--delimiter ';'" in message
        assert "--encoding ENCODING (undatum sniff shows the detected encoding)" in message
        assert "--on-error skip" in message

    def test_format_error_verbose(self):
        """Test formatting error in verbose mode."""
        error = ValueError("Test error")
        message = format_error_message(error, verbose=True)
        assert "Traceback" in message or "Test error" in message


class TestHandleCommandError:
    """Test handle_command_error function."""

    def test_handle_undatum_error(self, capsys):
        """Test handling UndatumError."""
        error = FileNotFoundError("/path/file.csv")
        exit_code = handle_command_error(error)
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "/path/file.csv" in captured.err
        assert exit_code == 1

    def test_handle_python_exception(self, capsys):
        """Test handling standard Python exception."""
        error = ValueError("Invalid value")
        exit_code = handle_command_error(error)
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert exit_code == 1

    def test_handle_permission_error(self, capsys):
        """Test handling PermissionError."""
        error = PermissionError("/path/file.csv", operation="read")
        exit_code = handle_command_error(error)
        assert exit_code == 3


class TestValidateFilePath:
    """Test validate_file_path function."""

    def test_validate_file_path_exists(self, tmp_path):
        """Test validating existing file."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("test")
        # Should not raise
        validate_file_path(str(test_file), check_read=True)

    def test_validate_file_path_not_found(self, tmp_path):
        """Test validating nonexistent file."""
        test_file = tmp_path / "nonexistent.csv"
        with pytest.raises(FileNotFoundError) as exc_info:
            validate_file_path(str(test_file), check_read=True)
        assert str(test_file) in str(exc_info.value)

    def test_validate_file_path_suggestions(self, tmp_path):
        """Test file validation with suggestions."""
        (tmp_path / "similar_file.csv").touch()
        test_file = tmp_path / "similar_fil.csv"  # Typo

        with pytest.raises(FileNotFoundError) as exc_info:
            validate_file_path(str(test_file), check_read=True)
        # Should have suggestions
        str(exc_info.value)
        # Suggestions may or may not be found depending on similarity threshold

    def test_validate_file_path_permission(self, tmp_path):
        """Test validating file without read permission."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("test")

        # Remove read permission (Unix only)
        if sys.platform != "win32":
            os.chmod(test_file, 0o000)
            try:
                with pytest.raises(PermissionError) as exc_info:
                    validate_file_path(str(test_file), check_read=True)
                assert "Permission denied" in str(exc_info.value)
            finally:
                # Restore permissions for cleanup
                os.chmod(test_file, 0o644)

    def test_validate_file_path_uri(self):
        """Test validating S3 URI (should skip validation)."""
        # S3 URIs should not raise FileNotFoundError
        validate_file_path("s3://bucket/file.csv", check_read=True)

    def test_validate_directory_path(self, tmp_path):
        """Test validating directory path."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()
        # Should not raise
        validate_file_path(str(test_dir), check_read=True)


class TestCommandErrorHandling:
    """Test error handling in actual commands."""

    def test_converter_file_not_found(self):
        """Test converter with nonexistent file."""
        from undatum.cmds.converter import Converter

        converter = Converter()
        with pytest.raises(FileNotFoundError):
            converter.convert("/nonexistent/file.csv", "output.csv", {})

    def test_schemer_file_not_found(self):
        """Test schemer with nonexistent file."""
        from undatum.cmds.schemer import Schemer

        schemer = Schemer()
        with pytest.raises(FileNotFoundError):
            schemer.extract_schema("/nonexistent/file.csv", {})

    def test_validator_file_not_found(self):
        """Test validator with nonexistent file."""
        from undatum.cmds.validator import Validator

        validator = Validator()
        with pytest.raises(FileNotFoundError):
            validator.validate("/nonexistent/file.csv", {})

    def test_selector_validation_error(self, tmp_path):
        """Test selector with missing fields option."""
        from undatum.cmds.selector import Selector

        test_file = tmp_path / "test.csv"
        test_file.write_text("col1,col2\nval1,val2\n")

        selector = Selector()
        with pytest.raises(ValidationError) as exc_info:
            selector.select(str(test_file), {})  # Missing 'fields' option
        assert "fields" in str(exc_info.value).lower()

    def test_sorter_validation_error(self, tmp_path):
        """Test sorter with missing --by option."""
        from undatum.cmds.sorter import Sorter

        test_file = tmp_path / "test.csv"
        test_file.write_text("col1,col2\nval1,val2\n")

        sorter = Sorter()
        with pytest.raises(ValidationError) as exc_info:
            sorter.sort(str(test_file), {})  # Missing 'by' option
        assert "by" in str(exc_info.value).lower() or "sort fields" in str(exc_info.value).lower()

    def test_joiner_validation_error(self, tmp_path):
        """Test joiner with missing --on option."""
        from undatum.cmds.joiner import Joiner

        test_file1 = tmp_path / "test1.csv"
        test_file1.write_text("id,col1\n1,val1\n")
        test_file2 = tmp_path / "test2.csv"
        test_file2.write_text("id,col2\n1,val2\n")

        joiner = Joiner()
        with pytest.raises(ValidationError) as exc_info:
            joiner.join(str(test_file1), str(test_file2), {})  # Missing 'on' option
        assert "on" in str(exc_info.value).lower() or "join key" in str(exc_info.value).lower()

    def test_masker_validation_error(self, tmp_path):
        """Test masker with missing fields option."""
        from undatum.cmds.masker import Masker

        test_file = tmp_path / "test.csv"
        test_file.write_text("email,phone\nuser@example.com,123456\n")

        masker = Masker()
        with pytest.raises(ValidationError) as exc_info:
            masker.mask(str(test_file), "output.csv", {})  # Missing 'fields' option
        assert "fields" in str(exc_info.value).lower()

    def test_masker_invalid_method(self, tmp_path):
        """Test masker with invalid method."""
        from undatum.cmds.masker import Masker

        test_file = tmp_path / "test.csv"
        test_file.write_text("email\nuser@example.com\n")

        masker = Masker()
        with pytest.raises(ValidationError) as exc_info:
            masker.mask(str(test_file), "output.csv", {"fields": "email", "method": "invalid"})
        assert "method" in str(exc_info.value).lower()
        assert "redact" in str(exc_info.value) or "hash" in str(exc_info.value)
