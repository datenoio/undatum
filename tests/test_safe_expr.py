"""Restricted evaluator for validation rule conditions."""

import pytest

from undatum.common.safe_expr import ExpressionError, SafeExpression
from undatum.common.validation_rules import ValidationRule, ValidationRuleError


def test_comparisons_and_boolean_logic():
    expr = SafeExpression("start_date <= end_date and amount > 0")
    assert expr.evaluate({"start_date": "2026-01-01", "end_date": "2026-02-01", "amount": 5})
    assert not expr.evaluate({"start_date": "2026-03-01", "end_date": "2026-02-01", "amount": 5})


def test_dotted_paths_and_functions():
    expr = SafeExpression("len(user.name) > 2 and lower(user.role) in ['admin', 'owner']")
    assert expr.evaluate({"user.name": "Alice", "user.role": "ADMIN"})


def test_backticks_allow_keyword_and_hyphen_names():
    expr = SafeExpression("`or` > 1 and `start-date` <= `end-date`")
    assert expr.evaluate({"or": 2, "start-date": "2026-01-01", "end-date": "2026-01-02"})


def test_declared_hyphen_fields_work_without_backticks():
    expr = SafeExpression("start-date <= end-date", fields=["start-date", "end-date"])
    assert expr.evaluate({"start-date": 1, "end-date": 2})


@pytest.mark.parametrize(
    "condition",
    [
        "().__class__.__bases__[0].__subclasses__()",
        "__import__('os').system('echo pwned')",
        "open('/etc/passwd').read()",
        "[x for x in range(3)]",
        "(lambda: 1)()",
        "data['key']",
    ],
)
def test_escape_attempts_are_rejected(condition):
    with pytest.raises(ExpressionError):
        SafeExpression(condition)


def test_cross_field_rule_rejects_unsafe_condition_at_load():
    with pytest.raises(ValidationRuleError):
        ValidationRule(
            {
                "type": "cross-field",
                "fields": ["a"],
                "condition": "().__class__.__bases__[0].__subclasses__()",
            }
        )


def test_cross_field_rule_with_field_named_or():
    rule = ValidationRule({"type": "cross-field", "fields": ["or"], "condition": "`or` >= 10"})
    assert rule.evaluate({"or": 12})[0] is True
    assert rule.evaluate({"or": 3})[0] is False
