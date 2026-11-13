"""Tests for filter matching."""

import pytest

from undatum.common.filter import match_filter, translate_filter_to_sql


class TestMatchFilter:
    """Test match_filter function."""

    def test_match_filter_empty(self):
        """Test filter with empty/None expression."""
        record = {"name": "Alice"}
        assert match_filter(record, None) is True
        assert match_filter(record, "") is True

    def test_match_filter_not_dict(self):
        """Test filter with non-dict record."""
        record = "not a dict"
        # Should return False for non-dict
        assert match_filter(record, "name") is False

    def test_match_filter_missing_field(self):
        """Test filter with missing field."""
        record = {"name": "Alice"}
        # Missing field should return False, not raise error
        assert match_filter(record, "missing_field") is False

    def test_match_filter_simple_field_access(self):
        """Test simple field access."""
        record = {"age": 30}
        # Bare identifier is truthy when the field is present and non-empty
        result = match_filter(record, "age")
        assert isinstance(result, bool)

    def test_match_filter_with_backticks(self):
        """Test filter with backtick-wrapped identifiers."""
        record = {"field-name": "value"}
        # Backticks should be stripped
        result = match_filter(record, "`field-name`")
        assert isinstance(result, bool)

    def test_match_filter_invalid_syntax(self):
        """Test filter with invalid syntax."""
        record = {"name": "Alice"}
        # Should handle invalid syntax gracefully
        try:
            result = match_filter(record, "invalid syntax !!!")
            assert isinstance(result, bool)
        except (ValueError, Exception):
            # Exception is acceptable for invalid syntax
            pass


class TestTranslateFilterToSql:
    """Test translate_filter_to_sql function."""

    def test_translate_filter_to_sql_none(self):
        """Test translate_filter_to_sql with None."""
        assert translate_filter_to_sql(None) is None
        assert translate_filter_to_sql("") is None

    def test_translate_simple_comparison(self):
        assert translate_filter_to_sql("age > 25") == 'TRY_CAST("age" AS DOUBLE) > 25'

    def test_translate_backtick_identifier(self):
        assert translate_filter_to_sql("`age` >= 30") == 'TRY_CAST("age" AS DOUBLE) >= 30'

    def test_translate_string_equality(self):
        assert translate_filter_to_sql("`status` == 'active'") == "\"status\" = 'active'"

    def test_translate_and_expression(self):
        sql = translate_filter_to_sql("age >= 30 AND status == 'active'")
        assert sql == 'TRY_CAST("age" AS DOUBLE) >= 30 AND "status" = \'active\''

    def test_translate_or_expression(self):
        sql = translate_filter_to_sql("age < 18 OR age > 65")
        assert " OR " in sql
        assert 'TRY_CAST("age" AS DOUBLE) < 18' in sql
        assert 'TRY_CAST("age" AS DOUBLE) > 65' in sql

    def test_translate_parentheses(self):
        sql = translate_filter_to_sql("(age >= 30 AND status == 'active') OR vip == true")
        assert sql is not None
        assert "OR" in sql
        assert "AND" in sql

    def test_translate_unsupported_returns_none(self):
        assert translate_filter_to_sql("name in ['a', 'b']") is None
        assert translate_filter_to_sql("user.name == 'x'") is None
        assert translate_filter_to_sql("name like '%foo%'") is None
        assert translate_filter_to_sql('match "Al.*" name') is None

    def test_translate_ampersand_logical_ops(self):
        sql = translate_filter_to_sql('age >= 30 && status == "active"')
        assert sql == 'TRY_CAST("age" AS DOUBLE) >= 30 AND "status" = \'active\''

    def test_translate_double_quoted_string(self):
        assert translate_filter_to_sql('status == "active"') == "\"status\" = 'active'"

    def test_translate_decimal_number(self):
        """Issue #128: a decimal literal is a number, not a dotted field."""
        assert translate_filter_to_sql("price > 9.99") == 'TRY_CAST("price" AS DOUBLE) > 9.99'
        assert translate_filter_to_sql("delta >= -0.5") == 'TRY_CAST("delta" AS DOUBLE) >= -0.5'

    def test_translate_string_with_dot_or_keyword(self):
        """Issue #128: dots and keywords inside quoted strings are literal text."""
        assert (
            translate_filter_to_sql("email == 'alice@example.com'")
            == "\"email\" = 'alice@example.com'"
        )
        assert translate_filter_to_sql('note == "sign in; like new"') == (
            "\"note\" = 'sign in; like new'"
        )


class TestMatchFilterExpressions:
    """Test comparison/boolean expressions used by commands."""

    def test_comparison_and_boolean(self):
        record = {"age": 30, "status": "active"}
        assert match_filter(record, "age >= 30") is True
        assert match_filter(record, "age < 18") is False
        assert match_filter(record, "age >= 30 AND status == 'active'") is True
        assert match_filter(record, 'age >= 30 && status == "active"') is True
        assert match_filter(record, "age < 18 OR status == 'active'") is True

    def test_in_workaround_with_or(self):
        record = {"status": "active"}
        assert match_filter(record, 'status == "active" || status == "pending"') is True
        assert match_filter(record, 'status == "inactive" || status == "pending"') is False

    def test_string_age_coerced_for_numeric_compare(self):
        record = {"age": "30"}
        assert match_filter(record, "age >= 18") is True
        assert match_filter(record, "age < 18") is False

    def test_unsupported_match_raises(self):
        record = {"name": "Alice"}
        with pytest.raises(ValueError, match="undatum sql"):
            match_filter(record, 'match "Al.*" name')

    def test_decimal_number(self):
        """Issue #128: ``price > 9.99`` compares numbers."""
        assert match_filter({"price": "10.5"}, "price > 9.99") is True
        assert match_filter({"price": "9.99"}, "price > 9.99") is False
        assert match_filter({"price": 9.99}, "price == 9.99") is True
        assert match_filter({"delta": "-1"}, "delta < -0.5") is True

    def test_string_with_dot(self):
        """Issue #128: a quoted string may contain dots."""
        record = {"email": "alice@example.com"}
        assert match_filter(record, "email == 'alice@example.com'") is True
        assert match_filter(record, 'email != "bob@example.com"') is True

    def test_keywords_inside_strings(self):
        record = {"note": "sign in; like new"}
        assert match_filter(record, "note == 'sign in; like new'") is True

    def test_dotted_field_still_rejected(self):
        with pytest.raises(ValueError, match="undatum sql"):
            match_filter({"user": {"name": "x"}}, "user.name == 'x'")
