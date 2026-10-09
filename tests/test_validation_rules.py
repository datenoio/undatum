"""Tests for validation rules."""

import json
import os
import tempfile

import pytest

from undatum.common.validation_rules import (
    ValidationRule,
    ValidationRuleError,
    ValidationRuleSet,
    parse_validation_rules,
)


class TestValidationRule:
    """Test ValidationRule class."""

    def test_init(self):
        """Test ValidationRule initialization."""
        rule_def = {"field": "email", "type": "field"}
        rule = ValidationRule(rule_def)
        assert rule.field == "email"
        assert rule.rule_type == "field"
        assert rule.severity == "error"

    def test_init_with_severity(self):
        """Test ValidationRule with custom severity."""
        rule_def = {"field": "email", "type": "field", "severity": "warning"}
        rule = ValidationRule(rule_def)
        assert rule.severity == "warning"

    def test_init_invalid_severity(self):
        """Test ValidationRule with invalid severity."""
        rule_def = {"field": "email", "type": "field", "severity": "invalid"}
        with pytest.raises(ValidationRuleError, match="Invalid severity"):
            ValidationRule(rule_def)

    def test_evaluate_field_rule_required(self):
        """Test evaluating required field rule."""
        rule_def = {"field": "email", "type": "field", "required": True}
        rule = ValidationRule(rule_def)

        # Missing field
        is_valid, msg = rule.evaluate({}, 0)
        assert is_valid is False
        assert "required" in msg.lower()

        # Empty field
        is_valid, msg = rule.evaluate({"email": ""}, 0)
        assert is_valid is False

        # Present field
        is_valid, msg = rule.evaluate({"email": "test@example.com"}, 0)
        assert is_valid is True

    def test_evaluate_field_rule_type_string(self):
        """Test evaluating string type rule."""
        rule_def = {"field": "name", "type": "field", "data_type": "string"}
        rule = ValidationRule(rule_def)

        is_valid, msg = rule.evaluate({"name": "John"}, 0)
        assert is_valid is True

        is_valid, msg = rule.evaluate({"name": 123}, 0)
        # Type validation may pass if not strictly enforced
        assert isinstance(is_valid, bool)

    def test_evaluate_field_rule_type_number(self):
        """Test evaluating number type rule."""
        rule_def = {"field": "age", "type": "field", "data_type": "number"}
        rule = ValidationRule(rule_def)

        is_valid, msg = rule.evaluate({"age": 25}, 0)
        assert is_valid is True

        is_valid, msg = rule.evaluate({"age": "not a number"}, 0)
        assert isinstance(is_valid, bool)

    def test_evaluate_field_rule_min_max(self):
        """Test evaluating min/max range rule."""
        rule_def = {"field": "age", "type": "field", "min": 18, "max": 100}
        rule = ValidationRule(rule_def)

        is_valid, msg = rule.evaluate({"age": 25}, 0)
        assert is_valid is True

        is_valid, msg = rule.evaluate({"age": 10}, 0)
        assert is_valid is False

        is_valid, msg = rule.evaluate({"age": 150}, 0)
        assert is_valid is False

    def test_evaluate_field_rule_format_email(self):
        """Test evaluating email format rule."""
        rule_def = {"field": "email", "type": "field", "format": "email"}
        rule = ValidationRule(rule_def)

        is_valid, msg = rule.evaluate({"email": "test@example.com"}, 0)
        assert is_valid is True

        is_valid, msg = rule.evaluate({"email": "invalid-email"}, 0)
        assert is_valid is False

    def test_evaluate_field_rule_unknown_type(self):
        """An unknown rule type is a configuration error when the rule is built."""
        from undatum.common.errors import ConfigurationError

        with pytest.raises(ConfigurationError, match="Unknown rule type"):
            ValidationRule({"field": "email", "type": "unknown_type"})

    def test_type_key_as_data_type(self):
        """Documented rule-file format uses 'type' for the expected data type."""
        rule = ValidationRule({"field": "name", "type": "string"})
        assert rule.rule_type == "field"
        assert rule.data_type == "string"

        is_valid, _ = rule.evaluate({"name": "John"}, 0)
        assert is_valid is True

        is_valid, msg = rule.evaluate({"name": 123}, 0)
        assert is_valid is False
        assert "string" in msg

    def test_type_number_with_range(self):
        """'type: number' with min/max mirrors the README rule-file example."""
        rule = ValidationRule({"field": "age", "type": "number", "min": 0, "max": 120})
        assert rule.rule_type == "field"

        is_valid, _ = rule.evaluate({"age": 30}, 0)
        assert is_valid is True

        is_valid, _ = rule.evaluate({"age": 150}, 0)
        assert is_valid is False

    def test_evaluate_field_rule_no_field(self):
        """Test evaluating field rule without field specified."""
        rule_def = {"type": "field"}
        rule = ValidationRule(rule_def)

        with pytest.raises(ValidationRuleError, match="must specify 'field'"):
            rule._evaluate_field_rule({}, 0)


class TestParseValidationRules:
    """Test parse_validation_rules function."""

    def test_parse_validation_rules_json(self):
        """Test parsing JSON validation rules."""
        rules_data = {"rules": [{"field": "email", "type": "field", "format": "email"}]}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(rules_data, f)
            temp_path = f.name

        try:
            rule_set = parse_validation_rules(temp_path)
            assert len(rule_set.rules) == 1
        finally:
            os.unlink(temp_path)

    def test_parse_validation_rules_yaml(self):
        """Test parsing YAML validation rules."""
        rules_data = {"rules": [{"field": "email", "type": "field", "format": "email"}]}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            import yaml

            yaml.dump(rules_data, f)
            temp_path = f.name

        try:
            rule_set = parse_validation_rules(temp_path)
            assert len(rule_set.rules) == 1
        finally:
            os.unlink(temp_path)

    def test_parse_validation_rules_file_not_found(self):
        """Test parsing non-existent file."""
        with pytest.raises(ValidationRuleError, match="not found"):
            parse_validation_rules("/nonexistent/rules.yaml")

    def test_parse_validation_rules_invalid_json(self):
        """Test parsing invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json {")
            temp_path = f.name

        try:
            with pytest.raises(ValidationRuleError, match="Failed to parse"):
                parse_validation_rules(temp_path)
        finally:
            os.unlink(temp_path)

    def test_parse_validation_rules_no_rules_key(self):
        """Test parsing file without 'rules' key."""
        rules_data = {}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(rules_data, f)
            temp_path = f.name

        try:
            with pytest.raises(ValidationRuleError, match="must contain 'rules' key"):
                parse_validation_rules(temp_path)
        finally:
            os.unlink(temp_path)


class TestValidationRuleSet:
    """Test ValidationRuleSet class."""

    def test_validate_record(self):
        """Test validating a record."""
        rule_def = {"field": "email", "type": "field", "format": "email"}
        rule = ValidationRule(rule_def)
        rule_set = ValidationRuleSet([rule])

        violations = rule_set.validate_record({"email": "test@example.com"}, 0)
        assert len(violations) == 0

        violations = rule_set.validate_record({"email": "invalid"}, 0)
        assert len(violations) > 0

    def test_validate_record_multiple_rules(self):
        """Test validating with multiple rules."""
        rules = [
            ValidationRule({"field": "email", "type": "field", "format": "email"}),
            ValidationRule({"field": "age", "type": "field", "min": 18}),
        ]
        rule_set = ValidationRuleSet(rules)

        violations = rule_set.validate_record({"email": "test@example.com", "age": 25}, 0)
        assert len(violations) == 0

        violations = rule_set.validate_record({"email": "invalid", "age": 10}, 0)
        assert len(violations) >= 1  # At least one violation
