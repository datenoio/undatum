"""Open Data Contract Standard (ODCS) contracts: check files against them, and write them.

An ODCS v3 contract (https://bitol-io.github.io/open-data-contract-standard/) describes a
dataset as schema objects with typed properties and quality checks. ``validate --rules`` reads
a contract like a rule file (:func:`read_contract`):

- the constraints of each property (``required``, ``unique``, ``primaryKey``, ``logicalType``,
  ``enum`` and the ``logicalTypeOptions`` undatum rules express) become one rule per
  property, checked record by record like a hand-written rule;
- the quality metrics (``nullValues``, ``missingValues``, ``invalidValues``,
  ``duplicateValues``, ``rowCount``) with their operators and units, composite primary keys
  and the options rules do not express (``exclusiveMinimum``, ``multipleOf``, ...) become
  contract checks, counted over the file in one pass (:func:`evaluate_checks`);
- the rest (``sql``, ``custom`` and ``text`` checks, unknown formats, ...) is listed as not
  checked. SQL checks are not run: a contract from elsewhere could run any SQL.

``schema --format odcs`` writes a contract for an inferred schema (:func:`contract_from_schema`).
"""

from __future__ import annotations

import math
import os
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..common.errors import ConfigurationError

ODCS_VERSION = "v3.2.0"
METRICS = ("nullValues", "missingValues", "invalidValues", "duplicateValues", "rowCount")
# ODCS 3.0 named library checks with "rule"
LEGACY_RULES = {"nullCheck": "nullValues", "duplicateCheck": "duplicateValues"}
OPERATORS = {
    "mustBe": lambda value, limit: value == limit,
    "mustNotBe": lambda value, limit: value != limit,
    "mustBeGreaterThan": lambda value, limit: value > limit,
    "mustBeGreaterOrEqualTo": lambda value, limit: value >= limit,
    "mustBeLessThan": lambda value, limit: value < limit,
    "mustBeLessOrEqualTo": lambda value, limit: value <= limit,
    "mustBeBetween": lambda value, limit: limit[0] <= value <= limit[1],
    "mustNotBeBetween": lambda value, limit: not limit[0] <= value <= limit[1],
}
SYMBOLS = {
    "mustBe": "=",
    "mustNotBe": "!=",
    "mustBeGreaterThan": ">",
    "mustBeGreaterOrEqualTo": ">=",
    "mustBeLessThan": "<",
    "mustBeLessOrEqualTo": "<=",
    "mustBeBetween": "between",
    "mustNotBeBetween": "not between",
}
# logicalType -> undatum rule keys
TYPE_RULES: dict[str, dict[str, str]] = {
    "integer": {"type": "integer"},
    "number": {"type": "number"},
    "boolean": {"format": "boolean"},
    "date": {"format": "date"},
    "timestamp": {"format": "datetime"},
    "string": {},
}
STRING_FORMATS = {"email", "uuid", "url"}
NUMERIC_CHECKS = ("exclusiveMinimum", "exclusiveMaximum", "multipleOf")


def is_contract(data: Any) -> bool:
    """Whether a parsed rule file is an ODCS data contract."""
    return isinstance(data, Mapping) and data.get("kind") == "DataContract"


@dataclass
class ContractCheck:
    """A check counted over the whole file: a metric compared with a limit.

    Args:
        name: Check name (its ``name`` or ``id``, or a generated one).
        metric: One of :data:`METRICS`.
        fields: Fields the metric reads (none for ``rowCount``).
        operator: Key of :data:`OPERATORS`.
        limit: Value the metric is compared with.
        unit: ``rows`` or ``percent`` (of the records).
        arguments: Metric arguments (``missingValues``, ``validValues``, ``pattern``, ...).
        severity: ``error``, ``warning`` or ``info``.
        description: Description from the contract.
    """

    name: str
    metric: str
    fields: tuple[str, ...]
    operator: str
    limit: Any
    unit: str = "rows"
    arguments: dict[str, Any] = field(default_factory=dict)
    severity: str = "error"
    description: str = ""


@dataclass
class Contract:
    """The rules, checks and unchecked parts of one schema object of a contract."""

    object_name: str
    rules: list[dict[str, Any]]
    checks: list[ContractCheck]
    not_checked: list[dict[str, str]]


def _field(prop: Mapping[str, Any]) -> str:
    return str(prop.get("physicalName") or prop.get("name"))


def _select_object(data: Mapping[str, Any], name: str | None, source: str) -> Mapping[str, Any]:
    objects = [obj for obj in data.get("schema") or [] if isinstance(obj, Mapping)]
    names = [str(obj.get("name")) for obj in objects]
    if name:
        for obj in objects:
            if name in (obj.get("name"), obj.get("physicalName")):
                return obj
        raise ConfigurationError(
            f"Data contract {source} has no schema object '{name}' (objects: {', '.join(names)})",
            config_key="rules",
        )
    if len(objects) == 1:
        return objects[0]
    if not objects:
        raise ConfigurationError(f"Data contract {source} has no schema", config_key="rules")
    raise ConfigurationError(
        f"Data contract {source} has several schema objects ({', '.join(names)}); "
        f"name one after '#', e.g. {source}#{names[0]}",
        config_key="rules",
    )


def _enum(values: Iterable[Any]) -> list[Any]:
    """Allowed values, with the text that CSV and other text formats hold for them."""
    allowed: list[Any] = []
    for item in values:
        value = item.get("value") if isinstance(item, Mapping) else item
        forms = [value]
        if isinstance(value, bool):
            forms += ["true" if value else "false", str(value)]
        elif isinstance(value, (int, float)):
            forms.append(str(value))
        for form in forms:  # True == 1, so compare types too
            if not any(type(seen) is type(form) and seen == form for seen in allowed):
                allowed.append(form)
    return allowed


def _search(pattern: str) -> str:
    """An ECMA-262 pattern (found anywhere in the value) for ``re.match`` (from the start)."""
    return pattern if pattern.startswith("^") else f"(?s:.*?)(?:{pattern})"


def _not_checked(name: str, reason: str) -> dict[str, str]:
    return {"name": name, "reason": reason}


def _property(
    prop: Mapping[str, Any], single_key: bool
) -> tuple[dict[str, Any] | None, list[ContractCheck], list[dict[str, str]]]:
    """The rule, checks and unchecked parts of one property."""
    field_name = _field(prop)
    label = str(prop.get("name") or field_name)
    rule: dict[str, Any] = {"field": field_name, "name": label}
    checks: list[ContractCheck] = []
    skipped: list[dict[str, str]] = []
    key = bool(prop.get("primaryKey")) and single_key
    if prop.get("required") or key:
        rule["required"] = True
    if prop.get("unique") or key:
        rule["unique"] = True

    logical = prop.get("logicalType")
    if logical in TYPE_RULES:
        rule.update(TYPE_RULES[logical])
    elif logical:
        skipped.append(_not_checked(label, f"logicalType '{logical}' is not checked"))

    options = prop.get("logicalTypeOptions") or {}
    for option, value in options.items():
        if logical == "string" and option in ("minLength", "maxLength"):
            rule["min_length" if option == "minLength" else "max_length"] = int(value)
        elif logical == "string" and option == "pattern":
            rule["pattern"] = _search(str(value))
        elif logical == "string" and option == "format" and str(value) in STRING_FORMATS:
            rule["format"] = str(value)
        elif logical in ("integer", "number") and option in ("minimum", "maximum"):
            rule["min" if option == "minimum" else "max"] = value
        elif logical in ("integer", "number") and option in NUMERIC_CHECKS:
            checks.append(
                ContractCheck(
                    f"{label} {option} {value}",
                    "invalidValues",
                    (field_name,),
                    "mustBe",
                    0,
                    arguments={option: value},
                )
            )
        elif logical in ("integer", "number") and option == "format":
            continue  # storage hints such as i64
        else:
            skipped.append(_not_checked(label, f"logicalTypeOptions.{option} is not checked"))

    if prop.get("enum"):
        rule["enum"] = _enum(prop["enum"])

    for quality in prop.get("quality") or []:
        check, reason = _quality(quality, (field_name,), label)
        if check is not None:
            checks.append(check)
        else:
            skipped.append(_not_checked(_quality_name(quality, label), reason))

    has_rule = len(rule) > 2
    return (rule if has_rule else None), checks, skipped


def _quality_name(quality: Mapping[str, Any], label: str) -> str:
    metric = quality.get("metric") or quality.get("rule") or quality.get("type") or "check"
    return str(quality.get("name") or quality.get("id") or f"{label} {metric}")


def _quality(
    quality: Mapping[str, Any], fields: tuple[str, ...], label: str
) -> tuple[ContractCheck | None, str]:
    """A quality item as a check, or ``None`` and why it is not checked."""
    if not isinstance(quality, Mapping):
        return None, "not a quality object"
    kind = quality.get("type") or "library"
    if kind != "library":
        reason = {
            "sql": "SQL checks are not run",
            "custom": "custom (vendor) checks are not run",
            "text": "text checks describe the data in words",
        }
        return None, reason.get(str(kind), f"type '{kind}' is not supported")
    rule = str(quality.get("rule"))
    metric = quality.get("metric") or LEGACY_RULES.get(rule, rule)
    if metric not in METRICS:
        return None, f"metric '{quality.get('metric') or quality.get('rule')}' is not supported"
    arguments = dict(quality.get("arguments") or {})
    if metric == "duplicateValues" and arguments.get("properties"):
        fields = tuple(str(name) for name in arguments["properties"])
    if metric in ("nullValues", "missingValues", "invalidValues") and not fields:
        return None, f"{metric} needs a property"
    operators = [name for name in OPERATORS if name in quality]
    if len(operators) != 1:
        return None, "needs exactly one operator (mustBe, mustBeLessThan, ...)"
    unit = str(quality.get("unit") or "rows")
    if unit not in ("rows", "percent"):
        return None, f"unit '{unit}' is not supported"
    severity = str(quality.get("severity") or "error")
    return (
        ContractCheck(
            _quality_name(quality, label),
            str(metric),
            fields if metric != "rowCount" else (),
            operators[0],
            quality[operators[0]],
            unit,
            arguments,
            severity if severity in ("error", "warning", "info") else "error",
            str(quality.get("description") or ""),
        ),
        "",
    )


def read_contract(
    data: Mapping[str, Any], object_name: str | None = None, source: str = "contract"
) -> Contract:
    """The undatum rules, checks and unchecked parts of a contract's schema object.

    Args:
        data: The parsed contract.
        object_name: Schema object to check (``name`` or ``physicalName``); needed when the
            contract has several.
        source: Contract path, for messages.

    Returns:
        :class:`Contract`

    Raises:
        ConfigurationError: The schema object is missing or ambiguous.
    """
    obj = _select_object(data, object_name, source)
    props = [prop for prop in obj.get("properties") or [] if isinstance(prop, Mapping)]
    keys = sorted(
        (prop for prop in props if prop.get("primaryKey")),
        key=lambda prop: prop.get("primaryKeyPosition", -1),
    )
    rules: list[dict[str, Any]] = []
    checks: list[ContractCheck] = []
    skipped: list[dict[str, str]] = []
    for prop in props:
        rule, prop_checks, prop_skipped = _property(prop, single_key=len(keys) == 1)
        if rule is not None:
            rules.append(rule)
        checks += prop_checks
        skipped += prop_skipped
    if len(keys) > 1:
        key_fields = tuple(_field(prop) for prop in keys)
        for prop in keys:
            rules.append({"field": _field(prop), "name": str(prop.get("name")), "required": True})
        checks.append(
            ContractCheck(
                f"primary key ({', '.join(key_fields)})", "duplicateValues", key_fields, "mustBe", 0
            )
        )
    by_name = {str(prop.get("name")): _field(prop) for prop in props}
    label = str(obj.get("name"))
    for quality in obj.get("quality") or []:
        check, reason = _quality(quality, (), label)
        if check is not None and check.metric == "duplicateValues":
            check.fields = tuple(by_name.get(name, name) for name in check.fields)
        if check is not None and (check.fields or check.metric == "rowCount"):
            checks.append(check)
        else:
            skipped.append(
                _not_checked(_quality_name(quality, label), reason or "needs a property")
            )
    return Contract(label, rules, checks, skipped)


# --------------------------------------------------------------------------- checks


def _empty(value: Any) -> bool:
    return value is None or value == ""


def _same(value: Any, other: Any) -> bool:
    if value is None or other is None:
        return value is None and other is None
    return value == other or str(value) == str(other)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class _Counter:
    """Counts one check's metric over the records."""

    def __init__(self, check: ContractCheck):
        self.check = check
        self.count = 0
        self._store: Any = None
        arguments = check.arguments
        self._missing = list(arguments.get("missingValues", [None, ""]))
        self._valid = arguments.get("validValues")
        pattern = arguments.get("pattern")
        self._pattern = re.compile(str(pattern)) if pattern else None

    def add(self, record: Mapping[str, Any], row: int) -> None:
        from ..common.validation_rules import lookup_field_values

        metric = self.check.metric
        if metric == "rowCount":
            return
        values = []
        for name in self.check.fields:
            found = lookup_field_values(record, name)
            values.append(found[0] if found else None)
        if metric == "duplicateValues":
            self._duplicate(values, row)
            return
        value = values[0]
        if metric == "nullValues":
            self.count += _empty(value)
        elif metric == "missingValues":
            self.count += any(_same(value, missing) for missing in self._missing) or (
                value == "" and None in self._missing
            )
        elif metric == "invalidValues" and not _empty(value):
            self.count += self._invalid(value)

    def _invalid(self, value: Any) -> bool:
        if self._valid is not None and not any(_same(value, valid) for valid in self._valid):
            return True
        if self._pattern is not None and not self._pattern.search(str(value)):
            return True
        number = _number(value)
        if number is None:
            return False  # the type rule reports values that are not numbers
        arguments = self.check.arguments
        if "exclusiveMinimum" in arguments and not number > float(arguments["exclusiveMinimum"]):
            return True
        if "exclusiveMaximum" in arguments and not number < float(arguments["exclusiveMaximum"]):
            return True
        step = _number(arguments.get("multipleOf"))
        if not step:
            return False
        return not math.isclose(number / step, round(number / step), abs_tol=1e-9)

    def _duplicate(self, values: list[Any], row: int) -> None:
        if all(_empty(value) for value in values):
            return
        if self._store is None:
            from ..common.validation_rules import _KeyStore

            self._store = _KeyStore()
        key = "\x1f".join("" if value is None else str(value) for value in values)
        if self._store.get(key) is not None:
            self.count += 1
        else:
            self._store.add(key, row)

    def result(self, rows: int) -> dict[str, Any]:
        if self._store is not None:
            self._store.close()
        check = self.check
        count = rows if check.metric == "rowCount" else self.count
        value: float = count
        if check.unit == "percent" and check.metric != "rowCount":
            value = round(count * 100 / rows, 6) if rows else 0.0
        try:
            passed = bool(OPERATORS[check.operator](value, check.limit))
        except (TypeError, IndexError):
            passed = False
        return {
            "name": check.name,
            "fields": list(check.fields),
            "metric": check.metric,
            "value": value,
            "unit": check.unit,
            "operator": check.operator,
            "limit": check.limit,
            "expected": f"{SYMBOLS[check.operator]} {check.limit}",
            "passed": passed,
            "severity": check.severity,
            "description": check.description,
        }


def evaluate_checks(
    checks: list[ContractCheck], records: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Count every check's metric in one pass over ``records`` and compare it with its limit.

    ``nullValues`` counts missing fields, nulls and empty values (CSV has no other null);
    ``invalidValues`` counts non-empty values; ``duplicateValues`` counts the records whose
    value (or combination of values) appeared before.

    Args:
        checks: Checks from :func:`read_contract`.
        records: The records of the file.

    Returns:
        One result per check: name, fields, metric, value, unit, operator, limit, expected,
        passed, severity, description
    """
    counters = [_Counter(check) for check in checks]
    rows = 0
    for row, record in enumerate(records):
        rows += 1
        for counter in counters:
            counter.add(record, row)
    return [counter.result(rows) for counter in counters]


# --------------------------------------------------------------------------- export

_LOGICAL_TYPES = (
    ("BOOL", "boolean"),
    ("TINYINT", "integer"),
    ("SMALLINT", "integer"),
    ("INTEGER", "integer"),
    ("BIGINT", "integer"),
    ("HUGEINT", "integer"),
    ("UTINYINT", "integer"),
    ("USMALLINT", "integer"),
    ("UINTEGER", "integer"),
    ("UBIGINT", "integer"),
    ("INT", "integer"),
    ("DOUBLE", "number"),
    ("FLOAT", "number"),
    ("REAL", "number"),
    ("DECIMAL", "number"),
    ("NUMERIC", "number"),
    ("TIMESTAMP", "timestamp"),
    ("DATETIME", "timestamp"),
    ("DATE", "date"),
    ("TIME", "time"),
    ("STRUCT", "object"),
    ("MAP", "map"),
    ("JSON", "object"),
)


def logical_type(physical: str, is_array: bool = False) -> str:
    """ODCS ``logicalType`` of a DuckDB type (``BIGINT`` -> ``integer``)."""
    text = physical.strip().upper()
    if is_array or text.endswith("[]") or text.startswith("LIST"):
        return "array"
    for prefix, logical in _LOGICAL_TYPES:
        if text.startswith(prefix):
            return logical
    return "string"


def contract_from_schema(table: Any, name: str | None = None) -> dict[str, Any]:
    """An ODCS contract (draft) for an inferred schema (``schema --format odcs``).

    Args:
        table: :class:`~undatum.cmds.schemer.TableSchema` of the file.
        name: Schema object name; the file name without extensions by default.

    Returns:
        The contract, ready to dump as YAML
    """
    source = os.path.basename(str(table.id or table.key or "data"))
    name = name or source.split(".")[0] or "data"
    properties = []
    for item in table.fields or []:
        prop: dict[str, Any] = {
            "name": item.name,
            "logicalType": logical_type(item.ftype, item.is_array),
            "physicalType": item.ftype,
        }
        if item.description:
            prop["description"] = item.description
        properties.append(prop)
    obj: dict[str, Any] = {
        "name": name,
        "physicalName": source,
        "physicalType": "file",
        "logicalType": "object",
        "properties": properties,
    }
    if table.description:
        obj["description"] = table.description
    return {
        "apiVersion": ODCS_VERSION,
        "kind": "DataContract",
        "id": str(uuid.uuid4()),
        "name": name,
        "version": "1.0.0",
        "status": "draft",
        "schema": [obj],
    }
