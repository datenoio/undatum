"""Filter matching for dictionary records.

Comparison and boolean expressions (``==``, ``!=``, ``<``, ``>``, ``<=``,
``>=``, ``AND``/``OR`` or ``&&``/``||``) are evaluated in-process. The same
subset is translated to SQL ``WHERE`` for DuckDB. Use ``undatum sql`` for
``LIKE``, ``IN``, joins, and other SQL.
"""

import logging
import re
from collections.abc import Iterator
from typing import Any

logger = logging.getLogger(__name__)

_MISSING = object()
_FILTER_HELP = (
    "Supported filters use comparisons (== != > < >= <=) with AND/OR "
    "(or &&/||). For SQL (LIKE, IN, joins), use undatum sql."
)


class _FilterTranslationError(Exception):
    """Raised when a filter expression cannot be translated or evaluated."""


def _iter_code_and_strings(expr: str) -> Iterator[tuple[str, str]]:
    """Yield ``("code"|"string", fragment)`` pairs, keeping quoted spans intact."""
    i = 0
    n = len(expr)
    while i < n:
        char = expr[i]
        if char in ("'", '"'):
            j = i + 1
            while j < n and expr[j] != char:
                j += 1
            if j < n:
                yield "string", expr[i : j + 1]
                i = j + 1
                continue
        j = i + 1
        while j < n and expr[j] not in ("'", '"'):
            j += 1
        yield "code", expr[i:j]
        i = j


def _rewrite_logical_ops(expr: str, and_token: str, or_token: str) -> str:
    """Normalize AND/OR/and/or/&&/|| outside of quoted strings."""
    parts = []
    for kind, fragment in _iter_code_and_strings(expr):
        if kind == "string":
            parts.append(fragment)
            continue
        fragment = re.sub(r"&&", and_token, fragment)
        fragment = re.sub(r"\|\|", or_token, fragment)
        fragment = re.sub(r"\bAND\b", and_token, fragment, flags=re.IGNORECASE)
        fragment = re.sub(r"\bOR\b", or_token, fragment, flags=re.IGNORECASE)
        parts.append(fragment)
    return "".join(parts)


def match_filter(record: dict, filter_expr: str | None) -> bool:
    """Match a record against a comparison/boolean filter expression.

    Args:
        record: Dictionary record to evaluate.
        filter_expr: Filter expression (e.g. ``age >= 18``, ``status == 'active'``).
            Empty or None matches every record.

    Returns:
        True if the record matches, False otherwise.

    Raises:
        ValueError: If the expression is invalid or uses unsupported syntax.
    """
    if filter_expr is None or not str(filter_expr).strip():
        return True

    if not isinstance(record, dict):
        logger.warning("match_filter: record is not a dict, returning False")
        return False

    try:
        normalized = _rewrite_logical_ops(str(filter_expr).strip(), "AND", "OR")
        return _eval_expr(record, normalized)
    except _FilterTranslationError as exc:
        raise ValueError(f'Invalid filter expression "{filter_expr}": {_FILTER_HELP}') from exc
    except Exception as exc:
        logger.debug(
            "Filter evaluation error: %s, expression: %s, record: %s",
            exc,
            filter_expr,
            record,
        )
        raise ValueError(f'Invalid filter expression "{filter_expr}": {exc}') from exc


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is _MISSING:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _parse_literal(token: str) -> Any:
    token = token.strip()
    if token.startswith("'") and token.endswith("'") and len(token) >= 2:
        return token[1:-1]
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        return token[1:-1]
    if re.match(r"^-?\d+\.\d+$", token):
        return float(token)
    if re.match(r"^-?\d+$", token):
        return int(token)
    if token.lower() == "true":
        return True
    if token.lower() == "false":
        return False
    raise _FilterTranslationError(f"unsupported value: {token}")


def _field_name(token: str) -> str:
    token = token.strip()
    if token.startswith("`") and token.endswith("`") and len(token) >= 2:
        return token[1:-1]
    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", token):
        return token
    raise _FilterTranslationError(f"unsupported identifier: {token}")


def _lookup(record: dict, token: str) -> Any:
    name = _field_name(token)
    if name not in record:
        return _MISSING
    return record[name]


def _compare(left: Any, op: str, right: Any) -> bool:
    if left is _MISSING:
        return False
    if op in (">", "<", ">=", "<="):
        left_n, right_n = _as_number(left), _as_number(right)
        if left_n is None or right_n is None:
            return False
        if op == ">":
            return left_n > right_n
        if op == "<":
            return left_n < right_n
        if op == ">=":
            return left_n >= right_n
        return left_n <= right_n

    if isinstance(right, bool) and isinstance(left, str):
        lowered = left.strip().lower()
        if lowered == "true":
            left = True
        elif lowered == "false":
            left = False
    elif isinstance(right, (int, float)) and not isinstance(right, bool):
        left_n = _as_number(left)
        if left_n is not None:
            left = left_n
            right = float(right)

    if op == "==":
        return bool(left == right)
    return bool(left != right)


def _eval_atom(record: dict, expr: str) -> bool:
    expr = expr.strip()
    if expr.lower() == "true":
        return True
    if expr.lower() == "false":
        return False
    value = _lookup(record, expr)
    if value is _MISSING:
        return False
    return bool(value)


def _eval_comparison(record: dict, expr: str) -> bool:
    expr = expr.strip()
    if expr.startswith("(") and _matching_outer_parens(expr):
        return _eval_expr(record, expr[1:-1].strip())
    if re.search(r"\bin\b|\blike\b|\bmatch\b|=>|\[|\.|;", expr, re.IGNORECASE):
        raise _FilterTranslationError("unsupported construct")
    try:
        left, op, right = _find_comparison_op(expr)
    except _FilterTranslationError:
        return _eval_atom(record, expr)
    return _compare(_lookup(record, left), op, _parse_literal(right))


def _eval_expr(record: dict, expr: str) -> bool:
    expr = expr.strip()
    if expr.startswith("(") and _matching_outer_parens(expr):
        return _eval_expr(record, expr[1:-1].strip())

    or_parts = _split_logical(expr, "OR")
    if len(or_parts) > 1:
        return any(_eval_expr(record, part) for part in or_parts)

    and_parts = _split_logical(expr, "AND")
    if len(and_parts) > 1:
        return all(_eval_expr(record, part) for part in and_parts)

    return _eval_comparison(record, expr)


def translate_filter_to_sql(filter_expr: str | None) -> str | None:
    """Translate basic filter expression to SQL WHERE clause.

    Supports comparisons (``==``, ``!=``, ``>=``, ``<=``, ``>``, ``<``),
    ``AND`` / ``OR`` (also ``&&`` / ``||``), parentheses, backtick identifiers,
    string literals (single or double quotes), numbers, and booleans.
    Returns ``None`` when translation is not possible (``IN``, ``LIKE``,
    nested dotted fields, and other constructs outside the comparison subset).

    Args:
        filter_expr: Filter expression string (e.g., "age >= 18")

    Returns:
        SQL WHERE clause string (without WHERE keyword) or None
    """
    if filter_expr is None or not str(filter_expr).strip():
        return None

    try:
        normalized = _rewrite_logical_ops(str(filter_expr).strip(), "AND", "OR")
        return _translate_expr(normalized)
    except _FilterTranslationError:
        return None


def _matching_outer_parens(expr: str) -> bool:
    if not (expr.startswith("(") and expr.endswith(")")):
        return False
    depth = 0
    for i, char in enumerate(expr):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0 and i != len(expr) - 1:
                return False
    return depth == 0


def _split_logical(expr: str, keyword: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_string = None
    i = 0
    n = len(expr)
    kw_pat = re.compile(rf"\s+{keyword}\s+", re.IGNORECASE)

    while i < n:
        char = expr[i]
        if in_string:
            buf.append(char)
            if char == in_string:
                in_string = None
            i += 1
            continue
        if char in ("'", '"'):
            in_string = char
            buf.append(char)
            i += 1
            continue
        if char == "(":
            depth += 1
            buf.append(char)
            i += 1
            continue
        if char == ")":
            depth -= 1
            buf.append(char)
            i += 1
            continue
        if depth == 0:
            match = kw_pat.match(expr, i)
            if match:
                part = "".join(buf).strip()
                if part:
                    parts.append(part)
                buf = []
                i = match.end()
                continue
        buf.append(char)
        i += 1

    part = "".join(buf).strip()
    if part:
        parts.append(part)
    return parts if len(parts) > 1 else [expr]


def _translate_expr(expr: str) -> str:
    expr = expr.strip()
    if expr.startswith("(") and _matching_outer_parens(expr):
        return f"({_translate_expr(expr[1:-1].strip())})"

    or_parts = _split_logical(expr, "OR")
    if len(or_parts) > 1:
        return " OR ".join(_translate_expr(part) for part in or_parts)

    and_parts = _split_logical(expr, "AND")
    if len(and_parts) > 1:
        return " AND ".join(_translate_expr(part) for part in and_parts)

    return _translate_comparison(expr)


def _find_comparison_op(expr: str) -> tuple[str, str, str]:
    in_string = None
    i = 0
    n = len(expr)
    ops = (">=", "<=", "==", "!=", ">", "<")

    while i < n:
        char = expr[i]
        if in_string:
            if char == in_string:
                in_string = None
            i += 1
            continue
        if char in ("'", '"'):
            in_string = char
            i += 1
            continue
        for op in ops:
            if expr[i : i + len(op)] == op:
                left = expr[:i]
                right = expr[i + len(op) :]
                if left.strip() and right.strip():
                    return left, op, right
                raise _FilterTranslationError("empty operand")
        i += 1

    raise _FilterTranslationError("no comparison operator")


def _translate_identifier(token: str) -> str:
    token = token.strip()
    if token.startswith("`") and token.endswith("`"):
        inner = token[1:-1].replace('"', '""')
        return f'"{inner}"'
    if token.startswith('"') and token.endswith('"'):
        return token
    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", token):
        return f'"{token}"'
    raise _FilterTranslationError(f"unsupported identifier: {token}")


def _translate_value(token: str) -> str:
    token = token.strip()
    if token.startswith("'") and token.endswith("'") and len(token) >= 2:
        inner = token[1:-1].replace("'", "''")
        return f"'{inner}'"
    if token.startswith('"') and token.endswith('"') and len(token) >= 2:
        inner = token[1:-1].replace("'", "''")
        return f"'{inner}'"
    if re.match(r"^-?\d+(?:\.\d+)?$", token):
        return token
    if token.lower() in ("true", "false"):
        return token.upper()
    raise _FilterTranslationError(f"unsupported value: {token}")


def _translate_comparison(expr: str) -> str:
    expr = expr.strip()
    if expr.startswith("(") and _matching_outer_parens(expr):
        return f"({_translate_expr(expr[1:-1].strip())})"

    if re.search(r"\bin\b|\blike\b|\bmatch\b|=>|\[|\.|;", expr, re.IGNORECASE):
        raise _FilterTranslationError("unsupported construct")

    left, op, right = _find_comparison_op(expr)
    sql_left = _translate_identifier(left)
    sql_right = _translate_value(right)
    sql_op = {"==": "=", "!=": "!=", ">=": ">=", "<=": "<=", ">": ">", "<": "<"}[op]

    if re.match(r"^-?\d", sql_right):
        sql_left = f"TRY_CAST({sql_left} AS DOUBLE)"

    return f"{sql_left} {sql_op} {sql_right}"
