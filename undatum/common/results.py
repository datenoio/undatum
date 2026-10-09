"""Machine-readable results of informational commands.

Informational commands (``count``, ``headers``, ``sniff``, ``stats``, ``schema``, ``diff``,
``validate``, ``analyze``, ``formats list``, ``config show``) print one JSON document with
``--json`` or ``--format-out json``. Its ``schema`` key names the layout and its major version,
for example ``undatum.count/1``; an incompatible change (a removed or renamed key, a changed
type) raises the version. :data:`SCHEMAS` documents every layout; the documentation site
publishes them as JSON Schema files.

In JSON mode errors are JSON too: one ``{"error": {...}}`` object on stderr, with the usual
exit codes (see :func:`error_document`).
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TextIO


@dataclass(frozen=True)
class ResultSchema:
    """Layout of one JSON result.

    Args:
        id: Schema id with major version, e.g. ``undatum.count/1``.
        command: Command that prints it.
        title: One-line description.
        properties: Top-level keys: ``key -> (JSON type, description)``.
        required: Keys that are always present (others may be missing).
    """

    id: str
    command: str
    title: str
    properties: dict[str, tuple[str, str]]
    required: tuple[str, ...] = field(default=())

    def json_schema(self) -> dict[str, Any]:
        """The layout as a JSON Schema (draft 2020-12) document."""
        props: dict[str, Any] = {"schema": {"const": self.id, "description": "Result layout"}}
        for key, (kind, description) in self.properties.items():
            types = kind.split("|")
            props[key] = {"type": types[0] if len(types) == 1 else types}
            props[key]["description"] = description
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": f"https://datenoio.github.io/undatum/schemas/{schema_file(self.id)}",
            "title": self.title,
            "description": f"Printed by `undatum {self.command} --json`.",
            "type": "object",
            "properties": props,
            "required": ["schema", *self.required],
        }


def schema_file(schema_id: str) -> str:
    """File name of a published schema: ``undatum.count/1`` -> ``undatum.count.v1.json``."""
    name, _, version = schema_id.partition("/")
    return f"{name}.v{version}.json"


SCHEMAS: dict[str, ResultSchema] = {}


def _register(schema: ResultSchema) -> ResultSchema:
    SCHEMAS[schema.id] = schema
    return schema


COUNT = _register(
    ResultSchema(
        "undatum.count/1",
        "count",
        "Number of records in a file",
        {"file": ("string", "Input path"), "rows": ("integer", "Number of records")},
        ("file", "rows"),
    )
)
HEADERS = _register(
    ResultSchema(
        "undatum.headers/1",
        "headers",
        "Field names of a file",
        {
            "file": ("string", "Input path"),
            "fields": ("array", "Field names in file order (nested fields as dotted paths)"),
        },
        ("file", "fields"),
    )
)
SNIFF = _register(
    ResultSchema(
        "undatum.sniff/1",
        "sniff",
        "Detected file properties",
        {
            "file": ("string", "Input path"),
            "filetype": ("string", "Detected format id (csv, jsonl, parquet, ...)"),
            "compression": ("string|null", "Compression codec (gz, zst, ...), null if none"),
            "encoding": ("string|null", "Text encoding, null for binary formats"),
            "delimiter": ("string|null", "Field delimiter of delimited text, else null"),
            "has_header": ("boolean|null", "Whether the first line is a header (CSV/TSV)"),
            "record_count": ("integer", "Number of records"),
            "sample_size": ("integer", "Records sampled for field types"),
            "fields": ("object", "Field name -> type and up to 3 examples"),
        },
        ("file", "filetype", "record_count", "fields"),
    )
)
STATS = _register(
    ResultSchema(
        "undatum.stats/1",
        "stats",
        "Field statistics",
        {
            "count": ("integer", "Records profiled"),
            "num_fields": ("integer", "Number of fields"),
            "fieldtypes": ("object", "Field -> detected type"),
            "fields": ("array", "Per-field statistics"),
            "dictkeys": ("array", "Fields with few distinct values"),
            "dicts": ("object", "Value lists of the dictionary fields"),
            "debug": ("object", "Engine diagnostics (engine, timings); not stable"),
        },
        ("count", "num_fields", "fieldtypes", "fields"),
    )
)
SCHEMA = _register(
    ResultSchema(
        "undatum.schema/1",
        "schema",
        "Inferred table schema (undatum's own format)",
        {
            "id": ("string", "Table id (file name)"),
            "key": ("string", "Hash of the field list"),
            "num_cols": ("integer", "Number of fields"),
            "num_records": ("integer", "Records read (-1 when not counted)"),
            "is_flat": ("boolean", "No nested fields"),
            "description": ("string|null", "Description (with --autodoc)"),
            "fields": ("array", "Fields: name, ftype, is_array, description, ..."),
            "files": ("array|null", "Files with this schema (schema-bulk)"),
            "success": ("boolean", "Inference succeeded"),
            "error": ("string|null", "Error message when inference failed"),
        },
        ("fields",),
    )
)
SCHEMA_VALIDATION = _register(
    ResultSchema(
        "undatum.schema-validation/1",
        "schema --validate",
        "Rows checked against the inferred schema",
        {
            "valid": ("boolean", "No invalid rows"),
            "stats": ("object", "valid, invalid, total, errors_by_field"),
            "invalid_sample": ("array", "Up to 20 invalid rows with their errors"),
        },
        ("valid", "stats"),
    )
)
DIFF = _register(
    ResultSchema(
        "undatum.diff/1",
        "diff",
        "Records added, removed and changed between two files",
        {
            "file1": ("string", "Old file"),
            "file2": ("string", "New file"),
            "key": ("array|null", "Key fields (null: records compared whole)"),
            "summary": (
                "object",
                "file1_count, file2_count, added_count, removed_count, changed_count",
            ),
            "added": ("array", "Records only in file2 (not with --summary-only)"),
            "removed": ("array", "Records only in file1 (not with --summary-only)"),
            "changed": ("array", "Changed records with key, old and new (not with --summary-only)"),
        },
        ("file1", "file2", "summary"),
    )
)
SCHEMA_DIFF = _register(
    ResultSchema(
        "undatum.schema-diff/1",
        "diff --schema",
        "Schema changes between two files or declared schemas",
        {
            "old": ("string", "Baseline file or schema"),
            "new": ("string", "Compared file or schema"),
            "summary": ("object", "Changes per kind: added, removed, type, nullability"),
            "changes": ("array", "Changes: kind, field, old and new type or nullability"),
            "renames": ("array", "Likely renames: old, new, name_similarity, value_overlap"),
        },
        ("old", "new", "summary", "changes", "renames"),
    )
)
SCHEMA_DRIFT = _register(
    ResultSchema(
        "undatum.schema-drift/1",
        "schema-drift",
        "Schema changes of a set of files against a baseline",
        {
            "baseline": ("string", "Baseline file or schema"),
            "summary": ("object", "files (compared) and drifted (with changes)"),
            "files": ("array", "Per file: file, summary, changes, renames"),
        },
        ("baseline", "summary", "files"),
    )
)
VALIDATE = _register(
    ResultSchema(
        "undatum.validate/1",
        "validate --rules",
        "Rule-file validation report",
        {
            "statistics": (
                "object",
                "total_records, total_violations, errors, warnings, info, passed",
            ),
            "violations_by_field": ("object", "Field -> number of violations"),
            "violations_by_rule": ("object", "Rule -> number of violations"),
            "violations": ("array", "Violations (at most --max-violations)"),
        },
        ("statistics", "violations"),
    )
)
VALIDATE_RULES = _register(
    ResultSchema(
        "undatum.validate-rules/1",
        "validate --list-rules",
        "Built-in validation rules",
        {
            "rules": ("array", "Rules: name, description, params, extra"),
            "keys": ("object", "Rule-file keys that are checks (required, unique, ...)"),
        },
        ("rules", "keys"),
    )
)
VALIDATE_RULE = _register(
    ResultSchema(
        "undatum.validate-rule/1",
        "validate --rule",
        "Values checked against one built-in rule",
        {
            "rule": ("string", "Rule name, e.g. common.email"),
            "field": ("string", "Checked field"),
            "mode": ("string", "invalid, valid, all or stats"),
            "statistics": ("object", "total, invalid, novalue, share (percent invalid)"),
            "records": (
                "array",
                "Checked values with a FIELD_valid flag (omitted with --mode stats)",
            ),
        },
        ("rule", "field", "statistics"),
    )
)
QUALITY = _register(
    ResultSchema(
        "undatum.quality/1",
        "quality",
        "Data quality report with a pass/fail verdict",
        {
            "file": ("string", "Input path"),
            "summary": (
                "object",
                "rows, fields, empty_values, violations per severity (null without --rules)",
            ),
            "fields": (
                "array",
                "Per field: name, type, values, nulls, null_rate, distinct, conformance, top_values",
            ),
            "schema_check": (
                "object",
                "expected, inferred types, changes and renames against --schema",
            ),
            "violations": ("object", "by_severity, by_rule and a sample of rule violations"),
            "verdict": (
                "object",
                "passed and the threshold checks (name, target, value, limit, passed)",
            ),
        },
        ("file", "summary", "fields", "schema_check", "violations", "verdict"),
    )
)
ANALYZE = _register(
    ResultSchema(
        "undatum.analyze/1",
        "analyze",
        "File analysis report",
        {
            "filename": ("string", "Input path"),
            "file_size": ("integer", "Size in bytes"),
            "file_type": ("string", "Detected format id"),
            "compression": ("string", "Compression codec or raw"),
            "total_tables": ("integer", "Number of tables"),
            "total_records": ("integer", "Number of records"),
            "tables": ("array", "Per-table structure: fields, types, descriptions"),
            "metadata": ("object", "Encoding, delimiter and other file metadata"),
            "success": ("boolean", "Analysis succeeded"),
            "error": ("string|null", "Error message when analysis failed"),
        },
        ("filename", "tables"),
    )
)
FORMATS = _register(
    ResultSchema(
        "undatum.formats/1",
        "formats list",
        "Supported formats and their capabilities",
        {"formats": ("array", "Formats: id, readable, writable, ...")},
        ("formats",),
    )
)
CONFIG = _register(
    ResultSchema(
        "undatum.config/1",
        "config show",
        "Effective CLI configuration",
        {
            "files": ("object", "Config files read: home, project"),
            "defaults": ("object", "Merged command defaults"),
        },
        ("files", "defaults"),
    )
)


def envelope(schema: ResultSchema, payload: Mapping[str, Any]) -> dict[str, Any]:
    """``payload`` with ``schema`` as its first key (a legacy ``version`` key is dropped)."""
    document: dict[str, Any] = {"schema": schema.id}
    document.update((k, v) for k, v in payload.items() if k not in ("schema", "version"))
    return document


def dumps(document: Any) -> str:
    """Indented JSON text; non-JSON values (dates, decimals, ...) become strings."""
    from ..utils import normalize_for_json

    return json.dumps(normalize_for_json(document), indent=2, ensure_ascii=False, default=str)


def emit(
    schema: ResultSchema,
    payload: Mapping[str, Any],
    output: str | None = None,
    stream: TextIO | None = None,
) -> None:
    """Print (or write to ``output``) the JSON document of a result."""
    text = dumps(envelope(schema, payload))
    if output:
        with open(output, "w", encoding="utf8") as handle:
            handle.write(text + "\n")
        return
    out = stream or sys.stdout
    out.write(text + "\n")


# --------------------------------------------------------------------------- JSON mode


def json_requested(args: Sequence[str]) -> bool:
    """Whether a command line asks for JSON (``--json`` or ``--format-out json``)."""
    tokens = list(args)
    if "--" in tokens:
        tokens = tokens[: tokens.index("--")]
    for i, token in enumerate(tokens):
        if token == "--json":
            return True
        name, sep, value = token.partition("=")
        if name in ("--format-out", "-O"):
            value = value if sep else (tokens[i + 1] if i + 1 < len(tokens) else "")
            if value.lower() == "json":
                return True
        elif token.startswith("-O") and token[2:].lower() == "json":
            return True
    return False


def error_document(error: BaseException, exit_code: int) -> dict[str, Any]:
    """The JSON error object printed on stderr in JSON mode.

    ``{"error": {"code": "file_not_found", "message": "...", "exit_code": 1, "details": {...}}}``
    """
    from .errors import error_code

    message = getattr(error, "message", None) or str(error) or type(error).__name__
    info: dict[str, Any] = {"code": error_code(error), "message": message, "exit_code": exit_code}
    context = getattr(error, "context", None)
    if isinstance(context, Mapping):
        details = {k: v for k, v in context.items() if v is not None}
        if details:
            info["details"] = details
    return {"error": info}
