"""Data quality report: profile, schema conformance, rule violations and a pass/fail verdict.

``undatum quality data.csv --rules rules.yml --schema expected.json --thresholds q.yml``
profiles every field in one DuckDB pass (null rate, distinct values, top values, type and
type conformance), compares the inferred schema with an expected one, applies validation
rules, and checks thresholds. The command exits with 1 when a threshold fails, so the
report doubles as a data contract in CI.
"""

from __future__ import annotations

import html
import itertools
import json
from dataclasses import asdict, dataclass, field
from difflib import get_close_matches
from typing import Any

from ..common.errors import ConfigurationError, FileNotFoundError

TOP_VALUES = 5
SAMPLE_VIOLATIONS = 100
BATCH_ROWS = 10_000
THRESHOLD_KEYS = {
    "min_rows": "minimum number of records",
    "max_rows": "maximum number of records",
    "max_null_rate": "share of empty values per field ({field: rate} or a number for all)",
    "min_type_conformance": "share of values that fit the field's type ({field: share} or a number)",
    "max_error_violations": "rule violations with severity error",
    "max_warning_violations": "rule violations with severity warning",
    "schema": "strict (no added, removed or retyped fields) or additive (new fields allowed)",
}


@dataclass
class FieldQuality:
    """Quality measures of one field."""

    name: str
    type: str
    values: int
    nulls: int
    null_rate: float
    distinct: int
    conformance: float
    top_values: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Check:
    """One threshold and its outcome."""

    name: str
    target: str
    value: float | int | str | None
    limit: float | int | str
    passed: bool
    message: str = ""


# ------------------------------------------------------------------ thresholds


def load_thresholds(path: str | None) -> dict[str, Any]:
    """Thresholds from a YAML or JSON file (``{}`` without a file).

    Raises:
        ConfigurationError: Unknown keys or values of the wrong type (exit code 2).
    """
    if not path:
        return {}
    import os

    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path, encoding="utf8") as handle:
        text = handle.read()
    if path.lower().endswith(".json"):
        data = json.loads(text)
    else:
        import yaml

        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ConfigurationError(
            "The thresholds file must contain a mapping", config_key="thresholds"
        )
    for key, value in data.items():
        if key not in THRESHOLD_KEYS:
            close = get_close_matches(str(key), list(THRESHOLD_KEYS), n=1)
            hint = f" Did you mean {close[0]}?" if close else ""
            raise ConfigurationError(
                f"Unknown threshold '{key}'.{hint} Known: {', '.join(THRESHOLD_KEYS)}",
                config_key="thresholds",
            )
        if key == "schema":
            if value not in ("strict", "additive"):
                raise ConfigurationError(
                    "schema must be 'strict' or 'additive'", config_key="thresholds.schema"
                )
        elif key in ("max_null_rate", "min_type_conformance"):
            values = value.values() if isinstance(value, dict) else [value]
            if not all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in values):
                raise ConfigurationError(
                    f"{key} takes numbers between 0 and 1", config_key=f"thresholds.{key}"
                )
        elif not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ConfigurationError(
                f"{key} takes a non-negative integer", config_key=f"thresholds.{key}"
            )
    return data


def _per_field(setting: Any, fields: list[str]) -> dict[str, float]:
    if isinstance(setting, dict):
        default = setting.get("*")
        limits = {name: setting[name] for name in setting if name != "*"}
        if default is not None:
            for name in fields:
                limits.setdefault(name, default)
        return limits
    return dict.fromkeys(fields, setting)


def evaluate(
    thresholds: dict[str, Any],
    rows: int,
    fields: list[FieldQuality],
    schema_diff: Any | None,
    severities: dict[str, int],
) -> list[Check]:
    """Check every threshold."""
    checks: list[Check] = []
    by_name = {f.name: f for f in fields}
    if "min_rows" in thresholds:
        limit = thresholds["min_rows"]
        checks.append(Check("min_rows", "records", rows, limit, rows >= limit))
    if "max_rows" in thresholds:
        limit = thresholds["max_rows"]
        checks.append(Check("max_rows", "records", rows, limit, rows <= limit))
    for key, attribute, compare in (
        ("max_null_rate", "null_rate", lambda v, lim: v <= lim),
        ("min_type_conformance", "conformance", lambda v, lim: v >= lim),
    ):
        if key not in thresholds:
            continue
        for name, limit in _per_field(thresholds[key], list(by_name)).items():
            measured = by_name.get(name)
            if measured is None:
                checks.append(Check(key, name, None, limit, False, f"field '{name}' not found"))
                continue
            value = getattr(measured, attribute)
            checks.append(Check(key, name, value, limit, bool(compare(value, limit))))
    for key, severity in (("max_error_violations", "error"), ("max_warning_violations", "warning")):
        if key in thresholds:
            count = severities.get(severity, 0)
            checks.append(Check(key, severity, count, thresholds[key], count <= thresholds[key]))
    if "schema" in thresholds:
        mode = thresholds["schema"]
        if schema_diff is None:
            checks.append(Check("schema", mode, None, mode, False, "no --schema to compare with"))
        else:
            counts = schema_diff.summary()
            failing = (
                counts["removed"] + counts["type"] + (counts["added"] if mode == "strict" else 0)
            )
            checks.append(
                Check("schema", mode, failing, 0, failing == 0, "changes that break the contract")
            )
    return checks


# ------------------------------------------------------------------ profiling


def _load(conn: Any, source: Any) -> None:
    """Make the records of ``source`` the DuckDB view or table ``data`` (text values)."""
    relation = source.duckdb_from()
    if relation is not None:
        conn.execute(f"CREATE VIEW data AS SELECT * FROM {relation}")
        return
    import pyarrow as pa

    from ..ops.expr import _text

    columns: list[str] = []
    created = False
    iterator = iter(source)
    while True:
        batch = [r for r in itertools.islice(iterator, BATCH_ROWS) if isinstance(r, dict)]
        if not batch:
            break
        for row in batch:
            for key in row:
                if key not in columns:
                    if created:
                        quoted = '"' + key.replace('"', '""') + '"'
                        conn.execute(f"ALTER TABLE data ADD COLUMN {quoted} VARCHAR")
                    columns.append(key)
        table = pa.table(
            {
                name: pa.array([_text(r.get(name)) for r in batch], type=pa.string())
                for name in columns
            }
        )
        conn.register("__batch", table)
        if created:
            conn.execute("INSERT INTO data BY NAME SELECT * FROM __batch")
        else:
            conn.execute("CREATE TABLE data AS SELECT * FROM __batch")
            created = True
        conn.unregister("__batch")
    if not created:
        conn.execute("CREATE TABLE data (__empty VARCHAR)")


def profile(
    path: str, options: dict[str, Any] | None = None, expected: dict[str, str] | None = None
) -> tuple[int, list[FieldQuality]]:
    """Record count and per-field measures of a file.

    Args:
        path: Input file.
        options: Reader options.
        expected: Field -> normalized type to measure conformance against (else the type
            most values have).
    """
    import duckdb

    from ..io import RowSource
    from ..ops.expr import _value_sql, infer_types
    from .drift import normalize_type

    options = options or {}
    source = RowSource(path, options)
    conn = duckdb.connect()
    try:
        _load(conn, source)
        described = conn.sql("DESCRIBE SELECT * FROM data").fetchall()
        schema = {str(r[0]): str(r[1]).upper() for r in described if str(r[0]) != "__empty"}
        dominant = infer_types(conn, "data", schema)
        rows = int(conn.sql("SELECT count(*) FROM data").fetchone()[0])  # type: ignore[index]
        fields: list[FieldQuality] = []
        sql_types = {
            "integer": "BIGINT",
            "number": "DOUBLE",
            "date": "DATE",
            "datetime": "TIMESTAMP",
            "boolean": "BOOLEAN",
            "time": "TIME",
        }
        for name, kind in schema.items():
            column = '"' + name.replace('"', '""') + '"'
            text = f"CAST({column} AS VARCHAR)"
            value = _value_sql(text) if kind == "VARCHAR" else column
            target = (expected or {}).get(name) or normalize_type(dominant[name])
            if kind != "VARCHAR" or target not in sql_types:
                fits = f"count({value})"
            elif target == "integer":
                fits = f"count_if(regexp_matches({value}, '^[+-]?[0-9]{{1,18}}$'))"
            elif target == "boolean":
                fits = f"count_if(lower({value}) IN ('true', 'false'))"
            else:
                fits = f"count(TRY_CAST({value} AS {sql_types[target]}))"
            present, conforming, distinct = conn.sql(
                f"SELECT count({value}), {fits}, count(DISTINCT {value}) FROM data"
            ).fetchone()  # type: ignore[misc]
            top = conn.sql(
                f"SELECT {text} AS v, count(*) AS n FROM data WHERE ({value}) IS NOT NULL "
                f"GROUP BY 1 ORDER BY n DESC, v LIMIT {TOP_VALUES}"
            ).fetchall()
            nulls = rows - int(present)
            fields.append(
                FieldQuality(
                    name=name,
                    type=target if present else "null",
                    values=int(present),
                    nulls=nulls,
                    null_rate=round(nulls / rows, 6) if rows else 0.0,
                    distinct=int(distinct),
                    conformance=round(int(conforming) / int(present), 6) if present else 1.0,
                    top_values=[{"value": v, "count": int(n)} for v, n in top],
                )
            )
        return rows, fields
    finally:
        conn.close()


def _violations(
    path: str, rules: str, options: dict[str, Any]
) -> tuple[dict[str, int], list[dict[str, Any]], dict[str, int]]:
    """Counts per severity, a sample of violations, and counts per rule."""
    from ..common.validation_rules import parse_validation_rules
    from ..io import RowSource

    rule_set = parse_validation_rules(rules)
    severities = {"error": 0, "warning": 0, "info": 0}
    by_rule: dict[str, int] = {}
    sample: list[dict[str, Any]] = []
    try:
        for index, record in enumerate(RowSource(path, options)):
            if not isinstance(record, dict):
                continue
            for violation in rule_set.validate_record(record, index):
                severities[violation["severity"]] = severities.get(violation["severity"], 0) + 1
                by_rule[violation["rule"]] = by_rule.get(violation["rule"], 0) + 1
                if len(sample) < SAMPLE_VIOLATIONS:
                    sample.append(violation)
    finally:
        rule_set.close()
    return severities, sample, by_rule


def build_report(
    path: str,
    *,
    rules: str | None = None,
    schema: str | None = None,
    thresholds: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The quality report of ``path`` as plain data (the ``undatum.quality/1`` payload)."""
    import os

    from .drift import FieldInfo, compare, load_schema

    options = options or {}
    if "://" not in path and not os.path.exists(path):
        raise FileNotFoundError(path)
    limits = load_thresholds(thresholds)
    expected = load_schema(schema, options) if schema else None
    rows, fields = profile(path, options, {n: f.type for n, f in (expected or {}).items()})
    current = {f.name: FieldInfo(f.name, f.type, f.nulls > 0) for f in fields}
    schema_diff = compare(expected, current, schema or "", path) if expected is not None else None
    severities: dict[str, int] = {}
    sample: list[dict[str, Any]] = []
    by_rule: dict[str, int] = {}
    if rules:
        severities, sample, by_rule = _violations(path, rules, options)
    checks = evaluate(limits, rows, fields, schema_diff, severities)
    return {
        "file": path,
        "summary": {
            "rows": rows,
            "fields": len(fields),
            "empty_values": sum(f.nulls for f in fields),
            "violations": dict(severities) if rules else None,
        },
        "fields": [asdict(f) for f in fields],
        "schema_check": {
            "expected": schema,
            "inferred": {f.name: f.type for f in fields},
            "changes": [asdict(c) for c in schema_diff.changes] if schema_diff else [],
            "renames": [asdict(r) for r in schema_diff.renames] if schema_diff else [],
        },
        "violations": {"by_severity": severities, "by_rule": by_rule, "sample": sample},
        "verdict": {
            "passed": all(c.passed for c in checks),
            "checks": [asdict(c) for c in checks],
        },
    }


# ------------------------------------------------------------------ rendering


def _rate(value: float) -> str:
    return f"{value:.1%}"


def render_markdown(report: dict[str, Any]) -> str:
    """Markdown report."""
    verdict = report["verdict"]
    status = "PASSED" if verdict["passed"] else "FAILED"
    summary = report["summary"]
    lines = [
        f"# Data quality: `{report['file']}`",
        "",
        f"**{status}** — {summary['rows']} records, {summary['fields']} fields, "
        f"{summary['empty_values']} empty values",
        "",
    ]
    if verdict["checks"]:
        lines += [
            "## Thresholds",
            "",
            "| Check | Target | Value | Limit | Result |",
            "|---|---|---|---|---|",
        ]
        for c in verdict["checks"]:
            value = "" if c["value"] is None else c["value"]
            result = "pass" if c["passed"] else f"**fail** {c['message']}".rstrip()
            lines.append(f"| {c['name']} | `{c['target']}` | {value} | {c['limit']} | {result} |")
        lines.append("")
    lines += [
        "## Fields",
        "",
        "| Field | Type | Empty | Distinct | Type conformance | Top values |",
        "|---|---|---|---|---|---|",
    ]
    for f in report["fields"]:
        top = ", ".join(f"`{t['value']}` ({t['count']})" for t in f["top_values"][:3])
        lines.append(
            f"| `{f['name']}` | {f['type']} | {_rate(f['null_rate'])} | {f['distinct']} | "
            f"{_rate(f['conformance'])} | {top} |"
        )
    schema = report["schema_check"]
    if schema["expected"]:
        lines += ["", f"## Schema (expected: `{schema['expected']}`)", ""]
        if not schema["changes"]:
            lines.append("No differences.")
        for c in schema["changes"]:
            lines.append(f"- {c['kind']}: `{c['field']}` ({c['old']} → {c['new']})")
        for r in schema["renames"]:
            lines.append(f"- possible rename: `{r['old']}` → `{r['new']}`")
    violations = report["violations"]
    if report["summary"]["violations"] is not None:
        counts = ", ".join(f"{n} {s}" for s, n in violations["by_severity"].items())
        lines += ["", "## Rule violations", "", counts or "None.", ""]
        if violations["by_rule"]:
            lines += ["| Rule | Violations |", "|---|---|"]
            lines += [f"| {rule} | {n} |" for rule, n in violations["by_rule"].items()]
            lines.append("")
        for v in violations["sample"][:20]:
            lines.append(f"- row {v['row']}, `{v['field']}` ({v['severity']}): {v['message']}")
    return "\n".join(lines).rstrip() + "\n"


_CSS = """
body{font-family:system-ui,-apple-system,Segoe UI,sans-serif;margin:2rem auto;max-width:1100px;
color:#1f2328;background:#fff;padding:0 1rem}
h1{font-size:1.5rem}h2{font-size:1.15rem;margin-top:2rem}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border-bottom:1px solid #d0d7de;padding:.35rem .5rem;text-align:left;vertical-align:top}
th{background:#f6f8fa}.pass{color:#1a7f37}.fail{color:#cf222e;font-weight:600}
.badge{display:inline-block;padding:.15rem .6rem;border-radius:1rem;color:#fff}
.badge.pass{background:#1a7f37;color:#fff}.badge.fail{background:#cf222e;color:#fff}
.bar{background:#eaeef2;height:.5rem;border-radius:.25rem;min-width:80px}
.bar span{display:block;height:100%;border-radius:.25rem;background:#0969da}
code{background:#f6f8fa;padding:0 .2rem;border-radius:.2rem}
@media (prefers-color-scheme: dark){body{background:#0d1117;color:#e6edf3}
th{background:#161b22}th,td{border-color:#30363d}code{background:#161b22}.bar{background:#30363d}}
"""


def render_html(report: dict[str, Any]) -> str:
    """Standalone HTML report (no external resources)."""
    e = html.escape
    verdict = report["verdict"]
    summary = report["summary"]
    status = "pass" if verdict["passed"] else "fail"
    parts = [
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Data quality: {e(report['file'])}</title><style>{_CSS}</style></head><body>",
        f"<h1>Data quality: <code>{e(report['file'])}</code></h1>",
        f"<p><span class='badge {status}'>{'PASSED' if verdict['passed'] else 'FAILED'}</span> "
        f"{summary['rows']} records, {summary['fields']} fields, "
        f"{summary['empty_values']} empty values</p>",
    ]
    if verdict["checks"]:
        parts.append(
            "<h2>Thresholds</h2><table><tr><th>Check</th><th>Target</th><th>Value</th><th>Limit</th><th>Result</th></tr>"
        )
        for c in verdict["checks"]:
            result = "pass" if c["passed"] else f"fail {e(c['message'])}"
            css = "pass" if c["passed"] else "fail"
            value = "" if c["value"] is None else e(str(c["value"]))
            parts.append(
                f"<tr><td>{e(c['name'])}</td><td><code>{e(str(c['target']))}</code></td>"
                f"<td>{value}</td><td>{e(str(c['limit']))}</td><td class='{css}'>{result}</td></tr>"
            )
        parts.append("</table>")
    parts.append(
        "<h2>Fields</h2><table><tr><th>Field</th><th>Type</th><th>Empty</th><th>Distinct</th>"
        "<th>Type conformance</th><th>Top values</th></tr>"
    )
    for f in report["fields"]:
        top = ", ".join(
            f"<code>{e(str(t['value']))}</code> ({t['count']})" for t in f["top_values"][:3]
        )
        filled = max(0.0, min(1.0, 1 - f["null_rate"]))
        parts.append(
            f"<tr><td><code>{e(f['name'])}</code></td><td>{e(f['type'])}</td>"
            f"<td>{_rate(f['null_rate'])}<div class='bar' title='filled'><span style='width:{filled:.0%}'></span></div></td>"
            f"<td>{f['distinct']}</td><td>{_rate(f['conformance'])}</td><td>{top}</td></tr>"
        )
    parts.append("</table>")
    schema = report["schema_check"]
    if schema["expected"]:
        parts.append(f"<h2>Schema (expected: <code>{e(schema['expected'])}</code>)</h2><ul>")
        if not schema["changes"]:
            parts.append("<li>No differences.</li>")
        for c in schema["changes"]:
            parts.append(
                f"<li>{e(c['kind'])}: <code>{e(c['field'])}</code> ({e(str(c['old']))} → {e(str(c['new']))})</li>"
            )
        for r in schema["renames"]:
            parts.append(
                f"<li>possible rename: <code>{e(r['old'])}</code> → <code>{e(r['new'])}</code></li>"
            )
        parts.append("</ul>")
    if summary["violations"] is not None:
        violations = report["violations"]
        parts.append("<h2>Rule violations</h2><p>")
        parts.append(
            ", ".join(f"{n} {e(s)}" for s, n in violations["by_severity"].items()) or "None."
        )
        parts.append("</p>")
        if violations["sample"]:
            parts.append(
                "<table><tr><th>Row</th><th>Field</th><th>Severity</th><th>Message</th></tr>"
            )
            for v in violations["sample"][:50]:
                parts.append(
                    f"<tr><td>{v['row']}</td><td><code>{e(str(v['field']))}</code></td>"
                    f"<td>{e(v['severity'])}</td><td>{e(v['message'])}</td></tr>"
                )
            parts.append("</table>")
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def write_report(report: dict[str, Any], format_out: str | None, output: str | None) -> None:
    """Write the report as JSON, Markdown or HTML (format from ``format_out`` or ``output``)."""
    from ..common.errors import ValidationError
    from ..common.results import QUALITY, dumps, envelope

    fmt = (format_out or "").lower()
    if not fmt and output:
        lower = output.lower()
        fmt = (
            "html"
            if lower.endswith((".html", ".htm"))
            else "json"
            if lower.endswith(".json")
            else "markdown"
        )
    fmt = {"md": "markdown", "": "markdown"}.get(fmt, fmt)
    if fmt == "json":
        text = dumps(envelope(QUALITY, report))
    elif fmt == "markdown":
        text = render_markdown(report)
    elif fmt == "html":
        text = render_html(report)
    else:
        raise ValidationError(
            f"Unsupported format '{format_out}'",
            field="format_out",
            suggestions=["html", "markdown", "json"],
        )
    if output:
        with open(output, "w", encoding="utf8") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
    else:
        print(text, end="" if text.endswith("\n") else "\n")
