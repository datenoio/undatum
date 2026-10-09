"""Restricted expression evaluator for validation rule conditions.

Rule files can come from other people, so conditions are never passed to ``eval``.
They are parsed with :mod:`ast` and only a small, documented subset is accepted:

- literals (numbers, strings, ``True``, ``False``, ``None``) and list/tuple literals;
- field references: plain names (``amount``), dotted paths (``user.age``) and
  backtick-quoted names for anything else (`` `start-date` ``, `` `or` ``);
- ``and``, ``or``, ``not``; ``+ - * / // %``; unary ``-``/``+``;
- comparisons ``== != < <= > >= in not in is is not`` (chains allowed);
- ``a if cond else b``;
- calls to the functions in :data:`FUNCTIONS`.

Anything else (attribute access on values, subscripts, lambdas, comprehensions,
calls to other names, dunder names) is rejected when the rule is loaded.
"""

from __future__ import annotations

import ast
import datetime
import operator
import re
from collections.abc import Iterable
from typing import Any


class ExpressionError(ValueError):
    """The condition uses unsupported syntax or unknown names."""


def _is_null(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _to_date(value: Any) -> datetime.date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(str(value)[:10])


FUNCTIONS: dict[str, Any] = {
    "len": len,
    "lower": lambda value: str(value).lower(),
    "upper": lambda value: str(value).upper(),
    "strip": lambda value: str(value).strip(),
    "is_null": _is_null,
    "int": int,
    "float": float,
    "str": str,
    "abs": abs,
    "min": min,
    "max": max,
    "date": _to_date,
}

_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}
_UNARY_OPS: dict[type, Any] = {
    ast.Not: operator.not_,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}
_COMPARE_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
    ast.Is: operator.is_,
    ast.IsNot: operator.is_not,
}
_IDENTIFIER_PATH = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_BACKTICK = re.compile(r"`([^`]+)`")


def _dotted_path(node: ast.AST) -> str | None:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


class SafeExpression:
    """A validated condition that can be evaluated against field values."""

    def __init__(self, text: str, fields: Iterable[str] = ()):
        """Parse and validate ``text``.

        Args:
            text: Condition such as ``"start_date <= end_date and amount > 0"``.
            fields: Declared field names; names that are not valid dotted
                identifiers (``start-date``) may then be used without backticks.

        Raises:
            ExpressionError: If the condition has a syntax error or unsupported construct.
        """
        self.text = text
        self._aliases: dict[str, str] = {}
        source = _BACKTICK.sub(lambda m: self._alias(m.group(1)), text)
        for field in sorted(fields, key=len, reverse=True):
            if not _IDENTIFIER_PATH.match(field):
                pattern = rf"(?<![\w.]){re.escape(field)}(?![\w.])"
                if re.search(pattern, source):
                    source = re.sub(pattern, self._alias(field), source)
        try:
            self._tree = ast.parse(source, mode="eval")
        except SyntaxError as exc:
            raise ExpressionError(f"Invalid condition '{text}': {exc.msg}") from exc
        self.field_names: set[str] = set()
        self._check(self._tree.body)

    def _alias(self, field: str) -> str:
        for alias, name in self._aliases.items():
            if name == field:
                return alias
        alias = f"_f{len(self._aliases)}"
        self._aliases[alias] = field
        return alias

    def _field_name(self, node: ast.AST) -> str:
        path = _dotted_path(node)
        if path is None:
            raise ExpressionError(
                f"Unsupported construct in condition '{self.text}': attribute access on a value"
            )
        if path in self._aliases:
            return self._aliases[path]
        if "__" in path:
            raise ExpressionError(f"Unsupported name '{path}' in condition '{self.text}'")
        return path

    def _check(self, node: ast.AST) -> None:
        if isinstance(node, ast.Constant):
            return
        if isinstance(node, (ast.Name, ast.Attribute)):
            self.field_names.add(self._field_name(node))
            return
        if isinstance(node, (ast.List, ast.Tuple)):
            for item in node.elts:
                self._check(item)
            return
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            for value in node.values:
                self._check(value)
            return
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
            self._check(node.operand)
            return
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            self._check(node.left)
            self._check(node.right)
            return
        if isinstance(node, ast.Compare) and all(type(op) in _COMPARE_OPS for op in node.ops):
            self._check(node.left)
            for comparator in node.comparators:
                self._check(comparator)
            return
        if isinstance(node, ast.IfExp):
            for part in (node.test, node.body, node.orelse):
                self._check(part)
            return
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in FUNCTIONS
            and not node.keywords
        ):
            for arg in node.args:
                self._check(arg)
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            raise ExpressionError(
                f"Unknown function '{node.func.id}' in condition '{self.text}'. "
                f"Allowed: {', '.join(sorted(FUNCTIONS))}"
            )
        raise ExpressionError(
            f"Unsupported construct in condition '{self.text}': {type(node).__name__}"
        )

    def evaluate(self, values: dict[str, Any]) -> Any:
        """Evaluate against ``values`` (field name -> value); missing fields are ``None``."""
        return self._eval(self._tree.body, values)

    def _eval(self, node: ast.AST, values: dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, (ast.Name, ast.Attribute)):
            return values.get(self._field_name(node))
        if isinstance(node, ast.List):
            return [self._eval(item, values) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(self._eval(item, values) for item in node.elts)
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result: Any = True
                for value in node.values:
                    result = self._eval(value, values)
                    if not result:
                        return result
                return result
            result = False
            for value in node.values:
                result = self._eval(value, values)
                if result:
                    return result
            return result
        if isinstance(node, ast.UnaryOp):
            return _UNARY_OPS[type(node.op)](self._eval(node.operand, values))
        if isinstance(node, ast.BinOp):
            return _BIN_OPS[type(node.op)](
                self._eval(node.left, values), self._eval(node.right, values)
            )
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, values)
            for op, comparator in zip(node.ops, node.comparators, strict=True):
                right = self._eval(comparator, values)
                if not _COMPARE_OPS[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            branch = node.body if self._eval(node.test, values) else node.orelse
            return self._eval(branch, values)
        if isinstance(node, ast.Call):
            func = FUNCTIONS[node.func.id]  # type: ignore[attr-defined]
            return func(*(self._eval(arg, values) for arg in node.args))
        raise ExpressionError(f"Unsupported construct: {type(node).__name__}")  # pragma: no cover
