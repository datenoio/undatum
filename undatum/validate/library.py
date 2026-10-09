"""Built-in validation rules: the catalogue behind ``format:`` in rule files.

Each rule checks one value. A rule file names it with ``format: <name>`` and may pass
parameters next to it (``formats`` for ``date``, ``region`` for ``phone``, ...)::

    rules:
      - field: country
        format: country
      - field: day
        format: date
        formats: ["%d.%m.%Y", "%Y-%m-%d"]

``undatum validate --list-rules`` prints the catalogue; ``docs/docs/commands/validate-rules.md``
is generated from it.
"""

from __future__ import annotations

import json
import re
import uuid as uuid_module
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from difflib import get_close_matches
from functools import cache
from importlib import resources
from typing import Any

from ..common.errors import ConfigurationError, DependencyError
from .commonrules import _validate_email, _validate_url
from .ruscodes import _check_inn, _check_ogrn

Check = Callable[[str, dict[str, Any]], bool]


@dataclass(frozen=True)
class RuleSpec:
    """One built-in rule.

    Args:
        name: Name used as ``format: <name>``.
        description: What a valid value looks like.
        check: ``check(value, params) -> bool``.
        params: Optional parameters: name -> description.
        extra: Optional dependency extra that the rule needs (``phone``).
    """

    name: str
    description: str
    check: Check
    params: dict[str, str] = field(default_factory=dict)
    extra: str | None = None


@cache
def _codes(resource: str, key: str) -> frozenset[str]:
    data = json.loads(
        resources.files("undatum.validate").joinpath("data").joinpath(resource).read_text()
    )
    return frozenset(data[key])


def _date(value: str, params: dict[str, Any]) -> bool:
    formats = params.get("formats") or params.get("date_formats")
    if not formats:
        try:
            date.fromisoformat(value)
            return True
        except ValueError:
            return False
    for pattern in [formats] if isinstance(formats, str) else formats:
        try:
            datetime.strptime(value, pattern)
            return True
        except ValueError:
            continue
    return False


def _datetime(value: str, params: dict[str, Any]) -> bool:
    formats = params.get("formats")
    if not formats:
        try:
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False
    return _date(value, {"formats": formats})


E164 = re.compile(r"^\+[1-9][0-9]{6,14}$")


def _phone(value: str, params: dict[str, Any]) -> bool:
    region = params.get("region")
    try:
        import phonenumbers
    except ImportError:
        if region:
            raise DependencyError(
                "phonenumbers",
                feature="national phone numbers (format: phone with region)",
                install_command='pip install "undatum[phone]"',
            ) from None
        return bool(E164.match(re.sub(r"[\s().-]", "", value)))
    try:
        number = phonenumbers.parse(value, region)
    except phonenumbers.NumberParseException:
        return False
    return bool(phonenumbers.is_valid_number(number))


def _country(value: str, params: dict[str, Any]) -> bool:
    alpha = str(params.get("alpha", "any"))
    text = value.strip().upper()
    if alpha in ("2", "any") and text in _codes("iso3166.json", "alpha_2"):
        return True
    if alpha in ("3", "any") and text in _codes("iso3166.json", "alpha_3"):
        return True
    return alpha == "numeric" and value.strip() in _codes("iso3166.json", "numeric")


def _currency(value: str, params: dict[str, Any]) -> bool:
    return value.strip().upper() in _codes("iso4217.json", "alpha_3")


def _language(value: str, params: dict[str, Any]) -> bool:
    text = value.strip().lower()
    if params.get("allow_region", True):
        text = re.split(r"[-_]", text, maxsplit=1)[0]
    return text in _codes("iso639.json", "alpha_2")


def _iban(value: str, params: dict[str, Any]) -> bool:
    text = re.sub(r"\s", "", value).upper()
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", text):
        return False
    rearranged = text[4:] + text[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def _uuid(value: str, params: dict[str, Any]) -> bool:
    try:
        uuid_module.UUID(value.strip())
        return True
    except ValueError:
        return False


def _pattern(value: str, params: dict[str, Any]) -> bool:
    regex = params.get("regex") or params.get("pattern")
    if not regex:
        raise ConfigurationError("format: pattern needs a 'regex' parameter", config_key="regex")
    return re.fullmatch(str(regex), value) is not None


def _integer(value: str, params: dict[str, Any]) -> bool:
    return re.fullmatch(r"[+-]?[0-9]+", value.strip()) is not None


def _number(value: str, params: dict[str, Any]) -> bool:
    try:
        float(value)
        return value.strip().lower() not in ("nan", "inf", "-inf", "infinity", "-infinity")
    except ValueError:
        return False


def _boolean(value: str, params: dict[str, Any]) -> bool:
    return value.strip().lower() in ("true", "false", "1", "0", "yes", "no")


RULES: dict[str, RuleSpec] = {
    spec.name: spec
    for spec in [
        RuleSpec("email", "An e-mail address (name@domain)", lambda v, p: bool(_validate_email(v))),
        RuleSpec("url", "An absolute URL", lambda v, p: bool(_validate_url(v))),
        RuleSpec(
            "date",
            "A calendar date; ISO 8601 (2026-10-08) unless 'formats' is given",
            _date,
            {"formats": "strptime patterns, e.g. ['%d.%m.%Y']"},
        ),
        RuleSpec(
            "datetime",
            "A date and time; ISO 8601 unless 'formats' is given",
            _datetime,
            {"formats": "strptime patterns"},
        ),
        RuleSpec(
            "phone",
            "A phone number: E.164 (+4930123456); national numbers with 'region'",
            _phone,
            {"region": "ISO country code for national numbers"},
            extra="phone",
        ),
        RuleSpec(
            "country",
            "An ISO 3166-1 country code (DE, DEU)",
            _country,
            {"alpha": "'2', '3', 'numeric' or 'any' (default)"},
        ),
        RuleSpec("currency", "An ISO 4217 currency code (EUR)", _currency),
        RuleSpec(
            "language",
            "An ISO 639-1 language code (en; en-GB with a region)",
            _language,
            {"allow_region": "accept a region suffix such as en-GB (default true)"},
        ),
        RuleSpec("iban", "An IBAN with a valid check sum", _iban),
        RuleSpec("uuid", "A UUID (any version)", _uuid),
        RuleSpec(
            "pattern",
            "The whole value matches a regular expression",
            _pattern,
            {"regex": "the regular expression"},
        ),
        RuleSpec("integer", "A whole number", _integer),
        RuleSpec("number", "A number (integer or decimal)", _number),
        RuleSpec("boolean", "true/false, yes/no or 1/0", _boolean),
        RuleSpec(
            "ru.org.inn",
            "A Russian taxpayer number (INN) with valid check digits",
            lambda v, p: bool(_check_inn(v)),
        ),
        RuleSpec(
            "ru.org.ogrn",
            "A Russian company registration number (OGRN)",
            lambda v, p: bool(_check_ogrn(v)),
        ),
    ]
}
# Historical names.
ALIASES = {"common.email": "email", "common.url": "url"}

# Rule-file keys that are checks rather than formats, for --list-rules.
KEY_RULES: dict[str, str] = {
    "required": "true: the field must be present and not empty (not_null)",
    "unique": "true: no value may repeat across the file",
    "min / max": "numeric range (inclusive)",
    "min_length / max_length": "text length range",
    "enum": "list of allowed values",
    "pattern": "regular expression the value must match (prefix match)",
    "references": "{file, field}: the value must exist in that field of another file",
    "condition": "cross-field rule: an expression over 'fields' (type: cross-field)",
}


def get_rule(name: str) -> RuleSpec:
    """The rule called ``name``.

    Raises:
        ConfigurationError: For an unknown name, with the closest names (exit code 2).
    """
    key = ALIASES.get(name, name)
    if key in RULES:
        return RULES[key]
    close = get_close_matches(name, [*RULES, *ALIASES], n=3)
    hint = f" Did you mean {', '.join(close)}?" if close else ""
    raise ConfigurationError(
        f"Unknown format '{name}'.{hint} Run 'undatum validate --list-rules' for the list.",
        config_key="format",
    )


def catalogue() -> list[dict[str, Any]]:
    """The rules as plain data (for --list-rules and the docs)."""
    return [
        {
            "name": spec.name,
            "description": spec.description,
            "params": dict(spec.params),
            "extra": spec.extra,
        }
        for spec in RULES.values()
    ]


def print_catalogue(format_out: str | None = None) -> None:
    """Print the rule catalogue (``validate --list-rules``) as a table or JSON."""
    if (format_out or "").lower() == "json":
        from ..common.results import VALIDATE_RULES, emit

        emit(VALIDATE_RULES, {"rules": catalogue(), "keys": dict(KEY_RULES)})
        return
    from rich.console import Console
    from rich.markup import escape
    from rich.table import Table

    table = Table(title="Built-in rules (format: NAME)", show_lines=False)
    table.add_column("Rule", style="bold")
    table.add_column("Checks")
    table.add_column("Parameters")
    for spec in RULES.values():
        params = "\n".join(f"{name}: {text}" for name, text in spec.params.items())
        if spec.extra:
            params = (params + "\n" if params else "") + f"(undatum[{spec.extra}] for all features)"
        table.add_row(escape(spec.name), escape(spec.description), escape(params))
    keys = Table(title="Rule keys", show_lines=False)
    keys.add_column("Key", style="bold")
    keys.add_column("Checks")
    for key, text in KEY_RULES.items():
        keys.add_row(escape(key), escape(text))
    console = Console()
    console.print(table)
    console.print(keys)
