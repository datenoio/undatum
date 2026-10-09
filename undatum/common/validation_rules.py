"""Validation rule parser and evaluator for rich validation rules."""

import json
import logging
import re
from pathlib import Path
from typing import Any

from .errors import ConfigurationError, UndatumError

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None  # type: ignore[assignment]

from ..utils import field_values as lookup_field_values
from ..validate import VALIDATION_RULEMAP
from .safe_expr import ExpressionError, SafeExpression

logger = logging.getLogger(__name__)


class ValidationRuleError(UndatumError):
    """Error parsing or evaluating validation rules (a user error: exit code 1)."""

    code = "invalid_rules"


DATA_TYPES = ("string", "number", "integer", "float", "boolean", "date")


# Values kept in memory before a uniqueness or reference check moves them to SQLite on disk.
MEMORY_KEYS = 1_000_000


class _KeyStore:
    """A set of text keys (with a row number) that spills to SQLite when it grows large."""

    def __init__(self) -> None:
        self._memory: dict[str, int] = {}
        self._db: Any = None

    def _spill(self) -> None:
        import sqlite3
        import tempfile

        handle = tempfile.NamedTemporaryFile(prefix="undatum-keys-", suffix=".db", delete=False)
        handle.close()
        self._path = handle.name
        self._db = sqlite3.connect(self._path)
        self._db.execute("CREATE TABLE k (v TEXT PRIMARY KEY, n INTEGER)")
        self._db.executemany("INSERT INTO k VALUES (?, ?)", self._memory.items())
        self._memory = {}

    def get(self, key: str) -> int | None:
        """The row number stored for ``key``, or ``None``."""
        if self._db is None:
            return self._memory.get(key)
        row = self._db.execute("SELECT n FROM k WHERE v = ?", (key,)).fetchone()
        return None if row is None else int(row[0])

    def add(self, key: str, row: int = 0) -> None:
        """Store ``key`` (the first row number wins)."""
        if self._db is None:
            self._memory.setdefault(key, row)
            if len(self._memory) > MEMORY_KEYS:
                self._spill()
        else:
            self._db.execute("INSERT OR IGNORE INTO k VALUES (?, ?)", (key, row))

    def close(self) -> None:
        """Remove the spill file."""
        if self._db is not None:
            import os

            self._db.close()
            self._db = None
            os.remove(self._path)


def _load_reference(spec: Any, base_dir: Path | None) -> tuple[_KeyStore, str]:
    """Values of ``references: {file, field}`` as a key store, and a label for messages."""
    if not isinstance(spec, dict) or not spec.get("file") or not spec.get("field"):
        raise ValidationRuleError("'references' needs 'file' and 'field'")
    path = Path(str(spec["file"]))
    if not path.exists() and base_dir is not None and (base_dir / path).exists():
        path = base_dir / path
    if not path.exists():
        raise ValidationRuleError(f"Reference file not found: {spec['file']}")
    from ..io import RowSource

    store = _KeyStore()
    field = str(spec["field"])
    for record in RowSource(str(path), {"format_in": spec.get("format")}):
        if isinstance(record, dict):
            for value in lookup_field_values(record, field):
                if value is not None and value != "":
                    store.add(str(value))
    return store, f"{spec['file']}:{field}"


class ValidationRule:
    """Represents a single validation rule."""

    def __init__(self, rule_def: dict[str, Any]):
        """Initialize validation rule from definition.

        Args:
            rule_def: Rule definition dictionary
        """
        self.rule_def = rule_def
        self.field = rule_def.get("field")
        # 'type' historically doubles as the rule discriminator ('field'/'cross-field')
        # and, in documented rule files, as the expected data type (e.g. 'string').
        raw_type = rule_def.get("type", "field")
        if raw_type in ("field", "cross-field"):
            self.rule_type = raw_type
            self.data_type = rule_def.get("data_type")
        elif raw_type in DATA_TYPES:
            self.rule_type = "field"
            self.data_type = raw_type
        else:
            self.rule_type = raw_type
            self.data_type = None
        self.severity = rule_def.get("severity", "error")
        self.name = rule_def.get("name", "")
        self.description = rule_def.get("description", "")
        self.base_dir: Path | None = rule_def.get("_base_dir")

        if self.rule_type not in ("field", "cross-field"):
            raise ConfigurationError(
                f"Unknown rule type '{self.rule_type}' in rule '{self.name or self.field}'. "
                f"Use 'field', 'cross-field' or a data type ({', '.join(DATA_TYPES)})",
                config_key="type",
            )
        if self.data_type and self.data_type not in DATA_TYPES:
            raise ConfigurationError(
                f"Unknown data type '{self.data_type}'. Use one of: {', '.join(DATA_TYPES)}",
                config_key="data_type",
            )
        from ..validate.library import ALIASES, RULES, get_rule

        self._format = get_rule(str(rule_def["format"])) if rule_def.get("format") else None
        custom = rule_def.get("custom")
        if custom and custom not in VALIDATION_RULEMAP:
            if custom in RULES or custom in ALIASES:
                self._custom_spec = get_rule(str(custom))
            else:
                get_rule(str(custom))  # raises with suggestions
        self.unique = bool(rule_def.get("unique"))
        self._seen: _KeyStore | None = None
        self._references: _KeyStore | None = None
        self._reference_label = ""

        # Validate severity
        if self.severity not in ("error", "warning", "info"):
            raise ValidationRuleError(
                f"Invalid severity: {self.severity}. Must be 'error', 'warning', or 'info'"
            )

        # Cross-field conditions are compiled once with the restricted evaluator; a
        # condition using unsupported syntax fails here, before any data is read.
        self._expression: SafeExpression | None = None
        if self.rule_type == "cross-field" and rule_def.get("condition"):
            try:
                self._expression = SafeExpression(
                    str(rule_def["condition"]), fields=rule_def.get("fields") or []
                )
            except ExpressionError as exc:
                raise ValidationRuleError(str(exc)) from exc

    def evaluate(self, record: dict[str, Any], record_index: int = 0) -> tuple[bool, str | None]:
        """Evaluate rule against a record.

        Args:
            record: Record to validate
            record_index: Index of record (for error messages)

        Returns:
            Tuple of (is_valid, error_message)
        """
        if self.rule_type == "field":
            return self._evaluate_field_rule(record, record_index)
        elif self.rule_type == "cross-field":
            return self._evaluate_cross_field_rule(record, record_index)
        else:
            raise ValidationRuleError(f"Unknown rule type: {self.rule_type}")

    def _evaluate_field_rule(
        self, record: dict[str, Any], record_index: int
    ) -> tuple[bool, str | None]:
        """Evaluate field-level rule."""
        if not self.field:
            raise ValidationRuleError("Field-level rule must specify 'field'")

        values = lookup_field_values(record, self.field)
        value = values[0] if len(values) > 0 else None

        # Check required
        if self.rule_def.get("required", False):
            if value is None or value == "":
                return False, f"Field '{self.field}' is required but is missing or empty"

        # Skip other validations if value is None/empty (unless required)
        if value is None or value == "":
            return True, None

        # Type validation
        expected_type = self.data_type
        if expected_type:
            type_valid, type_msg = self._validate_type(value, expected_type)
            if not type_valid:
                return False, type_msg

        # Format validation (built-in rule library)
        if self._format is not None:
            if not self._format.check(
                value if isinstance(value, str) else str(value), self.rule_def
            ):
                return (
                    False,
                    f"Field '{self.field}' value '{value}' is not a valid {self._format.name}",
                )

        # Reference: the value must exist in a field of another file
        if self.rule_def.get("references"):
            if self._references is None:
                self._references, self._reference_label = _load_reference(
                    self.rule_def["references"], self.base_dir
                )
            if self._references.get(str(value)) is None:
                return (
                    False,
                    f"Field '{self.field}' value '{value}' is not in {self._reference_label}",
                )

        # Uniqueness across the file
        if self.unique:
            if self._seen is None:
                self._seen = _KeyStore()
            key = str(value)
            first = self._seen.get(key)
            if first is not None:
                return (
                    False,
                    f"Field '{self.field}' value '{value}' is not unique (first in row {first})",
                )
            self._seen.add(key, record_index)

        # Range validation for numbers
        if isinstance(value, (int, float)) or (isinstance(value, str) and self._is_numeric(value)):
            num_value = float(value) if isinstance(value, str) else value
            if "min" in self.rule_def:
                if num_value < self.rule_def["min"]:
                    return (
                        False,
                        f"Field '{self.field}' value {value} is less than minimum {self.rule_def['min']}",
                    )
            if "max" in self.rule_def:
                if num_value > self.rule_def["max"]:
                    return (
                        False,
                        f"Field '{self.field}' value {value} is greater than maximum {self.rule_def['max']}",
                    )

        # Length validation for strings
        if isinstance(value, str):
            if "min_length" in self.rule_def:
                if len(value) < self.rule_def["min_length"]:
                    return (
                        False,
                        f"Field '{self.field}' length {len(value)} is less than minimum {self.rule_def['min_length']}",
                    )
            if "max_length" in self.rule_def:
                if len(value) > self.rule_def["max_length"]:
                    return (
                        False,
                        f"Field '{self.field}' length {len(value)} is greater than maximum {self.rule_def['max_length']}",
                    )

        # Enum/whitelist validation
        if "enum" in self.rule_def:
            allowed_values = self.rule_def["enum"]
            if value not in allowed_values:
                return (
                    False,
                    f"Field '{self.field}' value '{value}' is not in allowed values: {allowed_values}",
                )

        # Regex validation
        if "pattern" in self.rule_def:
            pattern = self.rule_def["pattern"]
            if not re.match(pattern, str(value)):
                return (
                    False,
                    f"Field '{self.field}' value '{value}' does not match pattern '{pattern}'",
                )

        # Custom validation function
        if "custom" in self.rule_def:
            custom_func_name = self.rule_def["custom"]
            if custom_func_name in VALIDATION_RULEMAP:
                passed = bool(VALIDATION_RULEMAP[custom_func_name](value))
            else:
                passed = self._custom_spec.check(str(value), self.rule_def)
            if not passed:
                return (
                    False,
                    f"Field '{self.field}' failed custom validation '{custom_func_name}'",
                )

        return True, None

    def _evaluate_cross_field_rule(
        self, record: dict[str, Any], record_index: int
    ) -> tuple[bool, str | None]:
        """Evaluate cross-field rule."""
        condition = self.rule_def.get("condition")
        fields = self.rule_def.get("fields", [])

        if not condition:
            raise ValidationRuleError("Cross-field rule must specify 'condition'")
        if not fields:
            raise ValidationRuleError("Cross-field rule must specify 'fields'")
        if self._expression is None:  # pragma: no cover - compiled in __init__
            raise ValidationRuleError("Cross-field condition was not compiled")

        # Resolve every field the condition references (declared or not).
        resolved_values = {}
        for field in set(fields) | self._expression.field_names:
            values = lookup_field_values(record, field)
            resolved_values[field] = values[0] if len(values) > 0 else None

        try:
            result = self._expression.evaluate(resolved_values)
        except Exception as e:
            logger.warning(f"Error evaluating cross-field condition '{condition}': {e}")
            return False, f"Error evaluating cross-field condition: {str(e)}"
        if not result:
            return False, f"Cross-field condition '{condition}' failed for fields {fields}"

        return True, None

    def _validate_type(self, value: Any, expected_type: str) -> tuple[bool, str | None]:
        """Validate value type."""
        type_map: dict[str, type | tuple[type, ...]] = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "float": float,
            "boolean": bool,
            "date": str,  # Date validation would need date parsing
        }

        if expected_type not in type_map:
            logger.warning(f"Unknown type '{expected_type}', skipping type validation")
            return True, None

        expected = type_map[expected_type]

        # Special handling for number/integer/float with string values
        if expected_type in ("number", "integer", "float") and isinstance(value, str):
            try:
                if expected_type == "integer":
                    int(value)
                elif expected_type == "float":
                    float(value)
                else:  # number
                    float(value)
                return True, None
            except ValueError:
                return False, f"Value '{value}' cannot be converted to {expected_type}"

        if isinstance(value, expected):
            return True, None
        else:
            return False, f"Value '{value}' is not of type {expected_type}"

    def _is_numeric(self, value: str) -> bool:
        """Check if string value is numeric."""
        try:
            float(value)
            return True
        except ValueError:
            return False


class ValidationRuleSet:
    """Collection of validation rules."""

    def __init__(self, rules: list[ValidationRule]):
        """Initialize rule set.

        Args:
            rules: List of ValidationRule objects
        """
        self.rules = rules

    @property
    def stateful(self) -> bool:
        """Whether a rule remembers values across records (``unique``)."""
        return any(rule.unique for rule in self.rules)

    def close(self) -> None:
        """Release the value stores of ``unique`` and ``references`` rules."""
        for rule in self.rules:
            for store in (rule._seen, rule._references):
                if store is not None:
                    store.close()

    def validate_record(
        self, record: dict[str, Any], record_index: int = 0
    ) -> list[dict[str, Any]]:
        """Validate a record against all rules.

        Args:
            record: Record to validate
            record_index: Index of record

        Returns:
            List of violation dictionaries
        """
        violations = []

        for rule in self.rules:
            is_valid, error_msg = rule.evaluate(record, record_index)
            if not is_valid:
                value = None
                if rule.field:
                    found = lookup_field_values(record, rule.field)
                    value = found[0] if found else None
                violations.append(
                    {
                        "rule": rule.name or f"Rule for {rule.field or 'cross-field'}",
                        "field": rule.field,
                        "severity": rule.severity,
                        "row": record_index,
                        "value": None if value is None else str(value)[:100],
                        "message": error_msg
                        or f"Validation failed for {rule.field or 'cross-field'}",
                        "rule_type": rule.rule_type,
                    }
                )

        return violations


def parse_validation_rules(file_path: str) -> ValidationRuleSet:
    """Parse validation rules from YAML or JSON file.

    Args:
        file_path: Path to rule file

    Returns:
        ValidationRuleSet object

    Raises:
        ValidationRuleError: If file cannot be parsed or is invalid
    """
    path = Path(file_path)
    if not path.exists():
        raise ValidationRuleError(f"Rule file not found: {file_path}")

    try:
        with open(path, encoding="utf-8") as f:
            if path.suffix.lower() in (".yaml", ".yml"):
                if not YAML_AVAILABLE:
                    raise ValidationRuleError(
                        "YAML support requires pyyaml. Install with: pip install pyyaml"
                    )
                data = yaml.safe_load(f)
            elif path.suffix.lower() == ".json":
                data = json.load(f)
            else:
                # Try to detect format
                content = f.read()
                f.seek(0)
                try:
                    data = json.loads(content)
                except json.JSONDecodeError as e:
                    if not YAML_AVAILABLE:
                        raise ValidationRuleError(
                            "YAML support requires pyyaml. Install with: pip install pyyaml"
                        ) from e
                    data = yaml.safe_load(content)
    except (yaml.YAMLError, json.JSONDecodeError) as e:
        raise ValidationRuleError(f"Failed to parse rule file: {e}") from e
    except Exception as e:
        raise ValidationRuleError(f"Error reading rule file: {e}") from e

    # Validate structure
    if not isinstance(data, dict):
        raise ValidationRuleError("Rule file must contain a dictionary/object")

    if "rules" not in data:
        raise ValidationRuleError("Rule file must contain 'rules' key")

    rules_list = data.get("rules", [])
    if not isinstance(rules_list, list):
        raise ValidationRuleError("'rules' must be a list")

    # Parse rules
    validation_rules = []
    for i, rule_def in enumerate(rules_list):
        if not isinstance(rule_def, dict):
            raise ValidationRuleError(f"Rule {i + 1} must be a dictionary/object")

        try:
            rule = ValidationRule({**rule_def, "_base_dir": path.parent})
            validation_rules.append(rule)
        except ConfigurationError:
            raise  # unknown rule, format or type names: exit code 2
        except Exception as e:
            raise ValidationRuleError(f"Error parsing rule {i + 1}: {e}") from e

    return ValidationRuleSet(validation_rules)
