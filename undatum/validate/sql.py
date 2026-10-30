"""Rule-file validation compiled to one DuckDB query, with the violations of the Python rules.

Each field rule becomes a ``CASE`` that returns the message of its first failing check, in the
order of :meth:`~undatum.common.validation_rules.ValidationRule._evaluate_field_rule`: required,
data type, references, unique, numeric range, length, enum, pattern. Values are the text of a
CSV or TSV file (``RowSource.duckdb_from()``), as the Python reader gives them.

A rule set compiles only when every rule does; otherwise (``format``, ``custom``, cross-field
conditions, patterns RE2 reads differently) the Python engine checks the records.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ASCII whitespace that Python's str.strip() removes (RE2's \s lacks \v and \x1c-\x1f).
_SPACE = r"[\t\n\x0b\x0c\r\x1c-\x1f ]"
_DIGITS = r"[0-9](?:_?[0-9])*"
# float() and int() grammars (ASCII digits: DuckDB casts only those).
_FLOAT = (
    rf"^{_SPACE}*[+-]?(?:(?:(?:{_DIGITS})?\.{_DIGITS}|{_DIGITS}\.?)(?:[eE][+-]?{_DIGITS})?"
    rf"|(?i:inf|infinity|nan)){_SPACE}*$"
)
_INTEGER = rf"^{_SPACE}*[+-]?{_DIGITS}{_SPACE}*$"
# A value outside ASCII that may be a number for Python (other digits, other spaces): only the
# Python engine can tell.
_PYTHON_ONLY_NUMBER = (
    r"^[\s\p{Z}\x85\x1c-\x1f\x0b]*[+-]?(?:[\p{Nd}_.]+(?:[eE][+-]?[\p{Nd}_]+)?"
    r"|(?i:inf|infinity|nan))[\s\p{Z}\x85\x1c-\x1f\x0b]*$"
)
NUMERIC_TYPES = ("number", "integer", "float")
_BATCH_ROWS = 10_000


def _lit(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def re2_pattern(pattern: str) -> str | None:
    """``pattern`` (Python ``re``) as an RE2 pattern with ``re.match`` semantics, or ``None``.

    Anchored at the start; ``\\d`` is ``\\p{Nd}`` (Unicode digits, as in Python); ``$`` also
    matches before a final newline and ``\\Z`` is ``\\z``. ``\\w``, ``\\s``, ``\\b`` and their
    negations, and ``\\D``, are Unicode-aware in Python but not in RE2: ``None``.
    """
    out: list[str] = []
    i = 0
    in_class = False
    while i < len(pattern):
        char = pattern[i]
        if char == "\\" and i + 1 < len(pattern):
            escaped = pattern[i + 1]
            if escaped == "d":
                out.append(r"\p{Nd}")
            elif escaped == "Z":
                out.append(r"\z")
            elif escaped in "DwWsSbB":
                return None
            else:
                out.append(char + escaped)
            i += 2
            continue
        if in_class:
            if char == "]":
                in_class = False
        elif char == "[":
            in_class = True
            out.append(char)
            i += 1
            # A ']' right after '[' or '[^' is a literal member of the class.
            if pattern.startswith("^", i):
                out.append("^")
                i += 1
            if pattern.startswith("]", i):
                out.append("]")
                i += 1
            continue
        elif char == "$":
            out.append(r"(?:\n?\z)")
            i += 1
            continue
        out.append(char)
        i += 1
    return "^(?:" + "".join(out) + ")"


class _Rule:
    """The SQL of one compiled rule: its message, and when Python must check the file."""

    def __init__(self, message: str, eligible_window: str | None, python_only: str | None):
        self.message = message
        # unique: the column of the first eligible row with the same value (window)
        self.eligible_window = eligible_window
        self.python_only = python_only


def _compile_rule(
    rule: Any, index: int, columns: set[str], references: list[str], conn: Any
) -> _Rule | None:
    """SQL for one field rule, or ``None`` when only the Python engine checks it."""
    spec = rule.rule_def
    if rule.rule_type != "field" or not rule.field:
        return None
    if spec.get("format") or spec.get("custom") or spec.get("condition"):
        return None
    field = str(rule.field)
    value = _quote(field) if field in columns else "CAST(NULL AS VARCHAR)"
    label = _lit(f"Field '{field}'")
    checks: list[tuple[str, str]] = []  # (condition, message)
    numeric_checks = False
    eligible: list[str] = []  # conditions a value passes before the unique check

    if spec.get("required", False):
        checks.append(
            (
                f"({value} IS NULL OR {value} = '')",
                _lit(f"Field '{field}' is required but is missing or empty"),
            )
        )
    checks.append((f"({value} IS NULL OR {value} = '')", "NULL"))

    data_type = rule.data_type
    if data_type in NUMERIC_TYPES:
        numeric_checks = True
        grammar = _INTEGER if data_type == "integer" else _FLOAT
        failed = f"NOT regexp_matches({value}, {_lit(grammar)})"
        checks.append((failed, f"'Value ''' || {value} || ''' cannot be converted to {data_type}'"))
        eligible.append(f"regexp_matches({value}, {_lit(grammar)})")
    elif data_type == "boolean":
        checks.append(("TRUE", f"'Value ''' || {value} || ''' is not of type boolean'"))
        eligible.append("FALSE")
    elif data_type not in (None, "string", "date"):
        return None

    if spec.get("references"):
        reference = _reference_relation(spec["references"], rule.base_dir, conn)
        if reference is None:
            return None
        name = f"__ref{index}"
        references.append(f"{name} AS ({reference[0]})")
        in_reference = f"{value} IN (SELECT k FROM {name})"
        checks.append(
            (
                f"NOT ({in_reference})",
                f"{label} || ' value ''' || {value} || ''' is not in ' || {_lit(reference[1])}",
            )
        )
        eligible.append(in_reference)

    eligible_window = None
    if rule.unique:
        condition = " AND ".join([f"NOT ({value} IS NULL OR {value} = '')", *eligible]) or "TRUE"
        eligible_window = f"min(CASE WHEN {condition} THEN __row END) OVER (PARTITION BY {value})"
        checks.append(
            (
                f"__row > __first{index}",
                f"{label} || ' value ''' || {value} || ''' is not unique (first in row ' "
                f"|| CAST(__first{index} AS VARCHAR) || ')'",
            )
        )

    number = (
        f"TRY_CAST(regexp_replace({value}, {_lit(f'^{_SPACE}+|{_SPACE}+$|_')}, '', 'g') AS DOUBLE)"
    )
    is_number = f"regexp_matches({value}, {_lit(_FLOAT)}) AND NOT isnan({number})"
    for key, sign, word in (
        ("min", "<", "less than minimum"),
        ("max", ">", "greater than maximum"),
    ):
        if key not in spec:
            continue
        bound = spec[key]
        if isinstance(bound, bool) or not isinstance(bound, (int, float)):
            return None
        if not math.isfinite(bound):
            return None
        numeric_checks = True
        checks.append(
            (
                f"{is_number} AND {number} {sign} {float(bound)!r}",
                f"{label} || ' value ' || {value} || ' is {word} ' || {_lit(str(bound))}",
            )
        )
    for key, sign, word in (
        ("min_length", "<", "less than minimum"),
        ("max_length", ">", "greater than maximum"),
    ):
        if key not in spec:
            continue
        bound = spec[key]
        if isinstance(bound, bool) or not isinstance(bound, (int, float)):
            return None
        checks.append(
            (
                f"length({value}) {sign} {bound!r}",
                f"{label} || ' length ' || CAST(length({value}) AS VARCHAR) || ' is {word} ' "
                f"|| {_lit(str(bound))}",
            )
        )
    if "enum" in spec:
        allowed = spec["enum"]
        if not isinstance(allowed, list):
            return None
        texts = [item for item in allowed if isinstance(item, str)]
        condition = f"{value} NOT IN ({', '.join(_lit(t) for t in texts)})" if texts else "TRUE"
        checks.append(
            (
                condition,
                f"{label} || ' value ''' || {value} || ''' is not in allowed values: ' "
                f"|| {_lit(str(allowed))}",
            )
        )
    if "pattern" in spec:
        pattern = str(spec["pattern"])
        translated = re2_pattern(pattern)
        if translated is None or not _re2_compiles(conn, translated):
            return None
        quoted = f"'{pattern}'"
        checks.append(
            (
                f"NOT regexp_matches({value}, {_lit(translated)})",
                f"{label} || ' value ''' || {value} || ''' does not match pattern ' "
                f"|| {_lit(quoted)}",
            )
        )

    message = "CASE " + " ".join(f"WHEN {c} THEN {m}" for c, m in checks) + " END"
    python_only = None
    if numeric_checks:
        python_only = (
            f"NOT regexp_matches({value}, '^[\\x00-\\x7F]*$') "
            f"AND regexp_matches({value}, {_lit(_PYTHON_ONLY_NUMBER)})"
        )
    return _Rule(message, eligible_window, python_only)


def _re2_compiles(conn: Any, pattern: str) -> bool:
    import duckdb

    try:
        conn.execute("SELECT regexp_matches('', ?)", [pattern]).fetchall()
    except duckdb.Error:
        return False
    return True


def _reference_relation(spec: Any, base_dir: Path | None, conn: Any) -> tuple[str, str] | None:
    """The non-empty values of a CSV reference file's field (SQL), and the message label."""
    from ..io import RowSource

    if not isinstance(spec, dict) or not spec.get("file") or not spec.get("field"):
        return None
    path = Path(str(spec["file"]))
    if not path.exists() and base_dir is not None and (base_dir / path).exists():
        path = base_dir / path
    if not path.exists():
        return None
    source = RowSource(str(path), {"format_in": spec.get("format")})
    relation = source.duckdb_from()
    if relation is None or source.format_id not in ("csv", "tsv"):
        return None
    field = str(spec["field"])
    columns = {str(row[0]) for row in conn.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()}
    if field not in columns:
        return None
    column = _quote(field)
    query = f"SELECT DISTINCT {column} AS k FROM {relation} WHERE {column} <> ''"
    return query, f"{spec['file']}:{field}"


def sql_violations(
    path: str, rule_set: Any, options: dict[str, Any] | None = None
) -> tuple[int, list[dict[str, Any]]] | None:
    """Records and violations of a CSV or TSV file checked by DuckDB, or ``None``.

    ``None`` when the file is not CSV/TSV text DuckDB reads, a rule or ``--filter`` does not
    compile, or a value is a number only Python reads: the Python engine checks the records.

    Args:
        path: Input file.
        rule_set: Parsed :class:`~undatum.common.validation_rules.ValidationRuleSet`.
        options: Command options (reader options, ``filter``).

    Returns:
        ``(number of records, violations)``, violations as ``validate_record()`` builds them,
        by row and rule order.
    """
    import duckdb

    from ..common.duckdb_config import duckdb_connection
    from ..common.filter import translate_filter_to_sql
    from ..io import RowSource

    options = options or {}
    source = RowSource(path, options)
    if source.format_id not in ("csv", "tsv"):
        return None
    relation = source.duckdb_from()
    if relation is None:
        return None
    filter_expr = options.get("filter")
    filter_sql = translate_filter_to_sql(filter_expr) if filter_expr else None
    if filter_expr and filter_sql is None:
        return None
    # Records are numbered in input order: one thread.
    conn = duckdb_connection(options, "ordered")
    try:
        columns = {
            str(row[0]) for row in conn.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
        }
        references: list[str] = []
        compiled = []
        for index, rule in enumerate(rule_set.rules):
            sql = _compile_rule(rule, index, columns, references, conn)
            if sql is None:
                logger.debug(
                    "validate: rule %s is checked by the Python engine", rule.name or rule.field
                )
                return None
            compiled.append(sql)
        windows = [
            f"{rule.eligible_window} AS __first{index}"
            for index, rule in enumerate(compiled)
            if rule.eligible_window
        ]
        kept = "SELECT * FROM __data" + (f" WHERE {filter_sql}" if filter_sql else "")
        if windows:
            kept = f"SELECT *, {', '.join(windows)} FROM ({kept})"
        selects = []
        python_only = []
        for index, (rule, spec) in enumerate(zip(compiled, rule_set.rules, strict=True)):
            field = str(spec.field)
            value = _quote(field) if field in columns else "CAST(NULL AS VARCHAR)"
            selects.append(
                f"SELECT __row, {index} AS __rule, {rule.message} AS __message, "
                f"left({value}, 100) AS __value FROM __kept"
            )
            if rule.python_only:
                python_only.append(f"({rule.python_only})")
        ctes = [
            f"__data AS (SELECT row_number() OVER () - 1 AS __row, * FROM {relation})",
            *references,  # before __kept: a unique rule's window may use them
            f"__kept AS ({kept})",
        ]
        with_clause = f"WITH {', '.join(ctes)}"
        if python_only:
            check = f"{with_clause} SELECT EXISTS (SELECT 1 FROM __kept WHERE {' OR '.join(python_only)})"
            if conn.execute(check).fetchall()[0][0]:
                logger.debug("validate: a value is a number only Python reads")
                return None
        total = int(conn.execute(f"SELECT count(*) FROM {relation}").fetchall()[0][0])
        result = conn.execute(
            f"{with_clause} SELECT * FROM ({' UNION ALL '.join(selects)}) "
            "WHERE __message IS NOT NULL ORDER BY __row, __rule"
        )
        # Rules and their report fields, built once; rows are fetched in batches
        labels = [
            (
                rule.name or f"Rule for {rule.field or 'cross-field'}",
                rule.field,
                rule.severity,
                rule.rule_type,
            )
            for rule in rule_set.rules
        ]
        violations = []
        while batch := result.fetchmany(_BATCH_ROWS):
            for row, index, message, value in batch:
                name, field, severity, rule_type = labels[index]
                violations.append(
                    {
                        "rule": name,
                        "field": field,
                        "severity": severity,
                        "row": int(row),
                        "value": value,
                        "message": message,
                        "rule_type": rule_type,
                    }
                )
    except duckdb.Error as exc:
        logger.debug("validate: DuckDB could not check the rules: %s", exc)
        return None
    finally:
        conn.close()
    return total, violations
