"""Schema diff and drift: added, removed, retyped and nullability-changed fields, and renames.

Field types are inferred strictly, like ``undatum schema``: a text column is an integer only
when every sampled value is one, so a stray value in a new delivery shows up as a type change.
Baselines can be data files or declared schemas (``undatum schema --json`` output, JSON Schema,
or a Frictionless table schema).
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Any

from ..common.errors import FileNotFoundError, ValidationError

SAMPLE_ROWS = 10_000
SAMPLE_VALUES = 200
CATEGORIES = ("added", "removed", "type", "nullability")
DATA_SUFFIXES = (".csv", ".tsv", ".json", ".jsonl", ".ndjson", ".parquet", ".xlsx", ".xml")


@dataclass
class FieldInfo:
    """What is known about one field.

    Args:
        name: Field name (nested fields as dotted paths).
        type: Normalized type: integer, number, boolean, date, datetime, time, string, object,
            array, binary or null (no values seen).
        nullable: Whether missing or empty values were seen (``None``: unknown).
        values: A sample of distinct values (data files only), for rename detection.
    """

    name: str
    type: str
    nullable: bool | None = None
    values: frozenset[str] = field(default_factory=frozenset, repr=False)


@dataclass
class Change:
    """One difference between two schemas."""

    kind: str  # added | removed | type | nullability
    field: str
    old: str | bool | None = None
    new: str | bool | None = None


@dataclass
class Rename:
    """A removed and an added field that are probably the same field."""

    old: str
    new: str
    name_similarity: float
    value_overlap: float | None


@dataclass
class SchemaDiff:
    """Differences between a baseline and a current schema."""

    old: str
    new: str
    changes: list[Change]
    renames: list[Rename]

    def summary(self) -> dict[str, int]:
        """Number of changes per kind."""
        return {kind: sum(1 for c in self.changes if c.kind == kind) for kind in CATEGORIES}

    def fails(self, fail_on: set[str]) -> bool:
        """Whether a change of a kind in ``fail_on`` (or ``any``) exists."""
        if "any" in fail_on:
            return bool(self.changes)
        return any(change.kind in fail_on for change in self.changes)

    def to_dict(self) -> dict[str, Any]:
        """The diff as plain data."""
        return {
            "old": self.old,
            "new": self.new,
            "summary": self.summary(),
            "changes": [asdict(c) for c in self.changes],
            "renames": [asdict(r) for r in self.renames],
        }


# ---------------------------------------------------------------- types


def normalize_type(kind: str | None) -> str:
    """A DuckDB, JSON Schema or Frictionless type name as one of the normalized types."""
    text = (kind or "").strip().upper()
    if not text or text == "NULL":
        return "null"
    if text.endswith("[]") or text.startswith(("LIST", "ARRAY")):
        return "array"
    if text.startswith(("STRUCT", "MAP", "OBJECT", "JSON", "UNION")):
        return "object"
    integer = ("BIGINT", "INTEGER", "INT", "SMALLINT", "TINYINT", "HUGEINT", "UBIGINT", "UINTEGER")
    if text in integer or text in ("USMALLINT", "UTINYINT", "UHUGEINT", "INT64", "INT32", "YEAR"):
        return "integer"
    if text.startswith(("DOUBLE", "FLOAT", "REAL", "DECIMAL", "NUMERIC", "NUMBER")):
        return "number"
    if text.startswith(("BOOL",)):
        return "boolean"
    if text == "DATE":
        return "date"
    if text.startswith(("TIMESTAMP", "DATETIME", "DATE-TIME")):
        return "datetime"
    if text.startswith("TIME"):
        return "time"
    if text in ("BLOB", "BYTEA", "BINARY", "VARBINARY"):
        return "binary"
    return "string"


# ---------------------------------------------------------------- profiles


def profile_file(path: str, options: dict[str, Any] | None = None) -> dict[str, FieldInfo]:
    """Fields of a data file, inferred from a sample of its records."""
    import duckdb

    from ..io import RowSource
    from ..ops.expr import _value_sql, infer_types

    if not os.path.exists(path) and "://" not in path:
        raise FileNotFoundError(path)
    options = options or {}
    source = RowSource(path, options)
    conn = duckdb.connect()
    try:
        relation = source.duckdb_from()
        if relation is None:
            relation = _register_sample(conn, source)
        else:
            relation = f"(SELECT * FROM {relation} LIMIT {SAMPLE_ROWS})"
        described = conn.sql(f"DESCRIBE SELECT * FROM {relation}").fetchall()
        schema = {str(row[0]): str(row[1]).upper() for row in described}
        types = infer_types(conn, relation, schema, min_share=1.0)
        fields: dict[str, FieldInfo] = {}
        for name, kind in types.items():
            column = '"' + name.replace('"', '""') + '"'
            # Missing: NULL, empty, or a placeholder such as n/a (as in type inference).
            empty = f"count_if(({_value_sql(f'CAST({column} AS VARCHAR)')}) IS NULL)"
            row = conn.sql(
                f"SELECT {empty}, list(DISTINCT CAST({column} AS VARCHAR)) "
                f"FILTER (WHERE {column} IS NOT NULL) FROM {relation}"
            ).fetchone()
            missing, values = row if row else (0, [])
            sample = frozenset(str(v) for v in (values or [])[:SAMPLE_VALUES])
            seen_type = normalize_type(kind) if sample else "null"
            fields[name] = FieldInfo(name, seen_type, bool(missing), sample)
        return fields
    finally:
        conn.close()


def _register_sample(conn: Any, source: Any) -> str:
    """Register a sample of a source DuckDB cannot read; return its relation (text values)."""
    import itertools

    import pyarrow as pa

    rows = [r for r in itertools.islice(source, SAMPLE_ROWS) if isinstance(r, dict)]
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)

    def text(value: Any) -> str | None:
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False, default=str)
        return str(value)

    table = pa.table(
        {
            f"c{i}": pa.array([text(r.get(n)) for r in rows], type=pa.string())
            for i, n in enumerate(columns)
        }
    )
    conn.register("__undatum_sample", table)
    renamed = ", ".join(
        f'c{i} AS "{n.replace(chr(34), chr(34) * 2)}"' for i, n in enumerate(columns)
    )
    return f"(SELECT {renamed or 'NULL AS __empty'} FROM __undatum_sample)"


def load_schema(path: str, options: dict[str, Any] | None = None) -> dict[str, FieldInfo]:
    """Fields of a baseline: a declared schema (JSON) or a data file."""
    if path.lower().endswith(".json") and os.path.isfile(path):
        try:
            with open(path, encoding="utf8") as handle:
                document = json.load(handle)
        except json.JSONDecodeError:
            document = None
        declared = _declared_fields(document) if isinstance(document, dict) else None
        if declared is not None:
            return declared
    return profile_file(path, options)


def _declared_fields(document: dict[str, Any]) -> dict[str, FieldInfo] | None:
    """Fields of ``undatum schema --json`` output, a JSON Schema, or a Frictionless schema."""
    if isinstance(document.get("properties"), dict):  # JSON Schema
        required = set(document.get("required") or [])
        fields = {}
        for name, spec in document["properties"].items():
            spec = spec if isinstance(spec, dict) else {}
            kind = spec.get("type")
            nullable = name not in required
            if isinstance(kind, list):
                nullable = nullable or "null" in kind
                kind = next((k for k in kind if k != "null"), None)
            if kind == "string" and spec.get("format") in ("date", "date-time", "time"):
                kind = {"date": "date", "date-time": "datetime", "time": "time"}[spec["format"]]
            fields[name] = FieldInfo(name, normalize_type(kind), nullable)
        return fields
    if isinstance(document.get("fields"), list):
        fields = {}
        for spec in document["fields"]:
            if not isinstance(spec, dict) or "name" not in spec:
                continue
            kind = spec.get("ftype") or spec.get("type")
            declared: bool | None = spec.get("nullable")
            constraints = spec.get("constraints") or {}
            if "required" in constraints:
                declared = not constraints["required"]
            fields[str(spec["name"])] = FieldInfo(str(spec["name"]), normalize_type(kind), declared)
        return fields
    return None


# ---------------------------------------------------------------- comparison


def compare(
    baseline: dict[str, FieldInfo], current: dict[str, FieldInfo], old: str = "", new: str = ""
) -> SchemaDiff:
    """Differences from ``baseline`` to ``current``."""
    changes: list[Change] = []
    for name, info in current.items():
        if name not in baseline:
            changes.append(Change("added", name, None, info.type))
    for name, info in baseline.items():
        if name not in current:
            changes.append(Change("removed", name, info.type, None))
            continue
        now = current[name]
        if "null" not in (info.type, now.type) and info.type != now.type:
            changes.append(Change("type", name, info.type, now.type))
        if info.nullable is not None and now.nullable is not None and info.nullable != now.nullable:
            changes.append(Change("nullability", name, info.nullable, now.nullable))
    removed = [baseline[c.field] for c in changes if c.kind == "removed"]
    added = [current[c.field] for c in changes if c.kind == "added"]
    return SchemaDiff(old, new, changes, _renames(removed, added))


def _renames(removed: list[FieldInfo], added: list[FieldInfo]) -> list[Rename]:
    """Likely renames: same type and a similar name or largely the same values."""
    candidates = []
    for gone in removed:
        for new in added:
            if "null" not in (gone.type, new.type) and gone.type != new.type:
                continue
            similarity = SequenceMatcher(None, gone.name.lower(), new.name.lower()).ratio()
            overlap = None
            if gone.values and new.values:
                overlap = len(gone.values & new.values) / len(gone.values | new.values)
            if similarity >= 0.6 or (overlap is not None and overlap >= 0.5):
                score = max(similarity, overlap or 0.0)
                candidates.append(
                    (
                        score,
                        Rename(
                            gone.name,
                            new.name,
                            round(similarity, 2),
                            None if overlap is None else round(overlap, 2),
                        ),
                    )
                )
    renames: list[Rename] = []
    used: set[str] = set()
    for _, rename in sorted(candidates, key=lambda c: -c[0]):
        if rename.old in used or rename.new in used:
            continue
        used.update((rename.old, rename.new))
        renames.append(rename)
    return renames


def expand_paths(patterns: list[str]) -> list[str]:
    """Files named by paths, directories and glob patterns, in a stable order."""
    files: list[str] = []
    for pattern in patterns:
        if os.path.isdir(pattern):
            for root, _dirs, names in sorted(os.walk(pattern)):
                files.extend(
                    os.path.join(root, n)
                    for n in sorted(names)
                    if n.lower().endswith(DATA_SUFFIXES)
                )
        elif any(ch in pattern for ch in "*?["):
            files.extend(sorted(glob.glob(pattern, recursive=True)))
        else:
            files.append(pattern)
    seen: dict[str, None] = {}
    for file in files:
        seen.setdefault(file, None)
    return list(seen)


def parse_fail_on(value: str | None) -> set[str]:
    """``--fail-on added,type`` -> ``{"added", "type"}`` (validated)."""
    if not value:
        return set()
    kinds = {v.strip().lower() for v in value.split(",") if v.strip()}
    allowed = {*CATEGORIES, "any"}
    unknown = kinds - allowed
    if unknown:
        raise ValidationError(
            f"Unknown --fail-on value(s): {', '.join(sorted(unknown))}",
            field="fail_on",
            suggestions=sorted(allowed),
        )
    return kinds


# ---------------------------------------------------------------- rendering


def render_text(diffs: list[SchemaDiff], baseline: str | None = None) -> str:
    """Human-readable report of one or more diffs."""
    lines = []
    if baseline:
        lines.append(f"Baseline: {baseline}")
    for diff in diffs:
        head = f"{diff.old} -> {diff.new}" if not baseline else diff.new
        if not diff.changes and not diff.renames:
            lines.append(f"{head}: no schema changes")
            continue
        summary = ", ".join(f"{n} {k}" for k, n in diff.summary().items() if n)
        lines.append(f"{head}: {summary}")
        for change in diff.changes:
            if change.kind == "added":
                lines.append(f"  + {change.field} ({change.new})")
            elif change.kind == "removed":
                lines.append(f"  - {change.field} ({change.old})")
            elif change.kind == "type":
                lines.append(f"  ~ {change.field}: {change.old} -> {change.new}")
            else:
                old = "nullable" if change.old else "required"
                new = "nullable" if change.new else "required"
                lines.append(f"  ~ {change.field}: {old} -> {new}")
        for rename in diff.renames:
            overlap = (
                "" if rename.value_overlap is None else f", {rename.value_overlap:.0%} same values"
            )
            lines.append(
                f"  ? {rename.old} -> {rename.new} looks like a rename "
                f"(name similarity {rename.name_similarity:.0%}{overlap})"
            )
    return "\n".join(lines)


def render_markdown(diffs: list[SchemaDiff], baseline: str | None = None) -> str:
    """Markdown report: one table of changes per file."""
    lines = ["# Schema drift" if baseline else "# Schema diff", ""]
    if baseline:
        lines += [f"Baseline: `{baseline}`", ""]
    for diff in diffs:
        lines += [f"## `{diff.new}`" if baseline else f"## `{diff.old}` → `{diff.new}`", ""]
        if not diff.changes and not diff.renames:
            lines += ["No schema changes.", ""]
            continue
        lines += ["| Change | Field | Before | After |", "|---|---|---|---|"]
        for c in diff.changes:
            lines.append(
                f"| {c.kind} | `{c.field}` | {c.old if c.old is not None else ''} | {c.new if c.new is not None else ''} |"
            )
        for r in diff.renames:
            lines.append(f"| rename? | `{r.old}` → `{r.new}` | | |")
        lines.append("")
    return "\n".join(lines)


def run_schema_diff(old: str, new: str, options: dict[str, Any]) -> SchemaDiff:
    """``diff --schema``: compare two files or declared schemas."""
    from ..io import side_options

    baseline = load_schema(old, side_options(options, 1))
    current = load_schema(new, side_options(options, 2))
    return compare(baseline, current, old, new)


def run_drift(
    paths: list[str], baseline: str | None, options: dict[str, Any]
) -> tuple[str, list[SchemaDiff]]:
    """``schema-drift``: compare every file with the baseline (default: the first file)."""
    files = expand_paths(paths)
    if not files:
        raise ValidationError("No files matched", field="paths")
    reference = baseline or files[0]
    base = load_schema(reference, options)
    diffs = [
        compare(base, profile_file(file, options), reference, file)
        for file in files
        if os.path.abspath(file) != os.path.abspath(reference)
    ]
    return reference, diffs


def emit_report(
    diffs: list[SchemaDiff],
    format_out: str | None,
    output: str | None,
    baseline: str | None = None,
) -> None:
    """Print or write a diff (one pair) or drift (``baseline`` set) report."""
    from ..common.results import SCHEMA_DIFF, SCHEMA_DRIFT, dumps, envelope

    fmt = (format_out or "").lower()
    if not fmt and output:
        fmt = (
            "json"
            if output.lower().endswith(".json")
            else "markdown"
            if output.lower().endswith(".md")
            else "text"
        )
    if fmt == "json":
        if baseline is None:
            text = dumps(envelope(SCHEMA_DIFF, diffs[0].to_dict()))
        else:
            files = [
                {"file": d.new, **{k: v for k, v in d.to_dict().items() if k not in ("old", "new")}}
                for d in diffs
            ]
            summary = {"files": len(diffs), "drifted": sum(1 for d in diffs if d.changes)}
            text = dumps(
                envelope(SCHEMA_DRIFT, {"baseline": baseline, "summary": summary, "files": files})
            )
    elif fmt in ("md", "markdown"):
        text = render_markdown(diffs, baseline)
    elif fmt in ("", "text"):
        text = render_text(diffs, baseline)
    else:
        raise ValidationError(
            f"Unsupported output format '{format_out}'",
            field="format_out",
            suggestions=["text", "markdown", "json"],
        )
    if output:
        with open(output, "w", encoding="utf8") as handle:
            handle.write(text + "\n")
    else:
        print(text)
