"""Tests for Validator class."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from undatum.cmds.validator import Validator
from undatum.common.errors import ValidationError


class TestValidator:
    """Test Validator class."""

    def test_init(self):
        """Test Validator initialization."""
        validator = Validator()
        assert validator is not None

    def test_validate_missing_fields_option(self):
        """Test validate without fields option in legacy mode."""
        validator = Validator()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"name": "Alice"}\n')
            temp_path = f.name

        try:
            options = {}  # No fields option
            with pytest.raises(ValidationError, match="requires --rules, or --fields"):
                validator.validate(temp_path, options)
        finally:
            os.unlink(temp_path)

    def test_validate_missing_rule_option(self):
        """Test validate without rule option in legacy mode."""
        validator = Validator()

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"email": "test@example.com"}\n')
            temp_path = f.name

        try:
            options = {"fields": "email"}  # No rule option
            with pytest.raises(ValidationError, match="requires --rule with --fields"):
                validator.validate(temp_path, options)
        finally:
            os.unlink(temp_path)

    @patch("undatum.cmds.validator.parse_validation_rules")
    def test_validate_with_rules_file(self, mock_parse_rules):
        """Test validate with rules file."""
        validator = Validator()

        mock_rule_set = MagicMock()
        mock_rule_set.validate_record.return_value = []
        mock_parse_rules.return_value = mock_rule_set

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            f.write('{"email": "test@example.com"}\n')
            temp_path = f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as rules_file:
            rules_path = rules_file.name

        try:
            options = {"rules": rules_path}
            # Should use rules file mode
            with patch("iterable.helpers.detect.open_iterable") as mock_open:
                mock_iterable = MagicMock()
                mock_iterable.__iter__ = MagicMock(
                    return_value=iter([{"email": "test@example.com"}])
                )
                mock_open.return_value = mock_iterable
                validator.validate(temp_path, options)
                mock_parse_rules.assert_called_once_with(rules_path)
        finally:
            os.unlink(temp_path)
            if os.path.exists(rules_path):
                os.unlink(rules_path)
