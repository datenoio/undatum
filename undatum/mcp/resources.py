"""MCP resources and prompts: datasets in the sandbox root, their schemas and samples.

Resources (JSON text):

- ``undatum://datasets`` — data files under the sandbox root, with format and size;
- ``undatum://dataset/{path}/schema`` — fields with inferred types and nullability;
- ``undatum://dataset/{path}/sample`` — the first records;
- ``undatum://formats`` — supported formats and whether they can be written.

``{path}`` is relative to the root; percent-encode ``/`` (``sub%2Fdata.csv``). Every path is
checked against the sandbox, and listings and samples are bounded.

Prompts (``profile-dataset``, ``draft-validation-rules``, ``plan-conversion``,
``document-dataset``) give an agent a ready plan that uses the undatum tools.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote

MAX_DATASETS = 500
MAX_DEPTH = 4
SAMPLE_RECORDS = 20
DATA_SUFFIXES = (
    ".csv",
    ".tsv",
    ".json",
    ".jsonl",
    ".ndjson",
    ".parquet",
    ".xlsx",
    ".xls",
    ".ods",
    ".xml",
    ".avro",
    ".orc",
    ".bson",
    ".feather",
    ".arrow",
    ".dbf",
    ".sqlite",
    ".duckdb",
)
COMPRESSION_SUFFIXES = (".gz", ".zst", ".zstd", ".bz2", ".xz", ".zip")


def _root() -> Path:
    from ..tools.sandbox import _SANDBOX

    return _SANDBOX.root or Path.cwd()


def _resolve(path: str) -> str:
    """A resource path (relative, percent-encoded) checked against the sandbox."""
    from ..tools.sandbox import _SANDBOX

    value = unquote(path)
    if _SANDBOX.root is None:
        return str(Path(value).resolve() if not Path(value).is_absolute() else Path(value))
    return _SANDBOX.resolve("path", value)


def _is_data_file(name: str) -> bool:
    lower = name.lower()
    for suffix in COMPRESSION_SUFFIXES:
        if lower.endswith(suffix):
            lower = lower[: -len(suffix)]
            break
    return lower.endswith(DATA_SUFFIXES)


def list_datasets() -> dict[str, Any]:
    """Data files under the root (at most ``MAX_DATASETS``, ``MAX_DEPTH`` levels deep)."""
    from ..common.format_names import format_from_name

    root = _root()
    found: list[dict[str, Any]] = []
    truncated = False
    for directory, dirnames, filenames in os.walk(root):
        depth = len(Path(directory).relative_to(root).parts)
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and depth < MAX_DEPTH)
        for name in sorted(filenames):
            if not _is_data_file(name):
                continue
            if len(found) >= MAX_DATASETS:
                truncated = True
                break
            full = Path(directory) / name
            relative = full.relative_to(root).as_posix()
            fast = format_from_name(name)
            encoded = quote(relative, safe="")
            found.append(
                {
                    "path": relative,
                    "format": fast[0] if fast else name.rsplit(".", 1)[-1].lower(),
                    "compression": fast[1] if fast else None,
                    "size": full.stat().st_size,
                    "schema": f"undatum://dataset/{encoded}/schema",
                    "sample": f"undatum://dataset/{encoded}/sample",
                }
            )
        if truncated:
            break
    return {"root": str(root), "datasets": found, "truncated": truncated}


def dataset_schema(path: str) -> dict[str, Any]:
    """Fields of a dataset with inferred types (strict, from a sample of 10,000 records)."""
    from ..cmds.drift import profile_file

    resolved = _resolve(path)
    fields = profile_file(resolved)
    return {
        "path": unquote(path),
        "fields": [
            {"name": f.name, "type": f.type, "nullable": f.nullable} for f in fields.values()
        ],
    }


def dataset_sample(path: str, limit: int = SAMPLE_RECORDS) -> dict[str, Any]:
    """The first records of a dataset (values made JSON-safe)."""
    import itertools

    from ..io import RowSource
    from ..utils import normalize_for_json

    resolved = _resolve(path)
    records = [normalize_for_json(r) for r in itertools.islice(RowSource(resolved, {}), limit)]
    return {"path": unquote(path), "records": records, "limit": limit}


def formats() -> dict[str, Any]:
    """Supported formats: id, writable, description."""
    from iterable.catalog import describe_format, list_formats

    rows = []
    for format_id in list_formats():
        try:
            info = describe_format(format_id)
        except Exception:  # noqa: BLE001 - a format whose extra is missing
            continue
        rows.append(
            {
                "id": info.get("id", format_id),
                "writable": bool(info.get("writable")),
                "description": info.get("description") or "",
            }
        )
    return {"formats": rows}


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _rule_names() -> str:
    from ..validate.library import RULES

    return ", ".join(RULES)


PROMPTS: dict[str, str] = {
    "profile-dataset": (
        "Profile the dataset at `{path}`.\n\n"
        "1. Call `sniff_file` for its format, encoding, delimiter and record count.\n"
        "2. Read the resource `undatum://dataset/{encoded}/schema` and call `compute_stats`.\n"
        "3. Report, field by field: type, share of empty values, distinct values, and anything\n"
        "   that looks wrong (mixed types, placeholders such as n/a, outliers, duplicates of\n"
        "   key-like fields).\n"
        "4. End with the three most important data quality issues and how to fix them."
    ),
    "draft-validation-rules": (
        "Draft an undatum validation rule file (YAML) for `{path}`.\n\n"
        "Read `undatum://dataset/{encoded}/schema` and `undatum://dataset/{encoded}/sample`.\n"
        "For each field choose checks that the sample supports: `required`, `unique`, `type`,\n"
        "`min`/`max`, `min_length`/`max_length`, `enum`, `pattern`, or `format` with one of:\n"
        "{rules}.\n"
        "Use `severity: warning` where you are unsure. Return only the YAML (top-level key\n"
        "`rules`), then explain each rule in one line. Do not invent fields."
    ),
    "plan-conversion": (
        "Plan the conversion of `{path}` to {target_format}.\n\n"
        "1. Call `detect_format` and read `undatum://dataset/{encoded}/schema`.\n"
        "2. Call `plan_conversion` with the source and a target path ending in\n"
        "   `.{target_format}`.\n"
        "3. List what may change (nested fields, types, dates, encodings) and the options that\n"
        "   control it.\n"
        "4. Only call `convert_file` with `confirm=true` after the user agrees."
    ),
    "document-dataset": (
        "Write Markdown documentation for the dataset `{path}`.\n\n"
        "Use `undatum://dataset/{encoded}/schema`, `undatum://dataset/{encoded}/sample` and\n"
        "`compute_stats`. Include: a one-paragraph description, the number of records, a table\n"
        "of fields (name, type, meaning, example, empty share), likely primary keys, and known\n"
        "limitations. Mark guesses about meaning as guesses."
    ),
}


def render_prompt(name: str, path: str, target_format: str = "parquet") -> str:
    """The text of prompt ``name`` for ``path``."""
    return PROMPTS[name].format(
        path=path,
        encoded=quote(path, safe=""),
        rules=_rule_names(),
        target_format=target_format,
    )


def register(mcp: Any) -> None:
    """Register the resources and prompts on an MCP server (mcp 1.x FastMCP or 2.x)."""

    @mcp.resource(
        "undatum://datasets",
        name="datasets",
        description="Data files under the server root, with format, size and resource links",
        mime_type="application/json",
    )
    def datasets_resource() -> str:
        return _json(list_datasets())

    @mcp.resource(
        "undatum://dataset/{path}/schema",
        name="dataset-schema",
        description="Fields of a dataset with inferred types; percent-encode '/' in path",
        mime_type="application/json",
    )
    def schema_resource(path: str) -> str:
        return _json(dataset_schema(path))

    @mcp.resource(
        "undatum://dataset/{path}/sample",
        name="dataset-sample",
        description=f"The first {SAMPLE_RECORDS} records of a dataset",
        mime_type="application/json",
    )
    def sample_resource(path: str) -> str:
        return _json(dataset_sample(path))

    @mcp.resource(
        "undatum://formats",
        name="formats",
        description="Supported data formats and whether undatum can write them",
        mime_type="application/json",
    )
    def formats_resource() -> str:
        return _json(formats())

    @mcp.prompt(name="profile-dataset", description="Profile a dataset and list quality issues")
    def profile_dataset(path: str) -> str:
        return render_prompt("profile-dataset", path)

    @mcp.prompt(name="draft-validation-rules", description="Draft a validation rule file")
    def draft_validation_rules(path: str) -> str:
        return render_prompt("draft-validation-rules", path)

    @mcp.prompt(name="plan-conversion", description="Plan converting a dataset to a format")
    def plan_conversion(path: str, target_format: str = "parquet") -> str:
        return render_prompt("plan-conversion", path, target_format)

    @mcp.prompt(name="document-dataset", description="Write Markdown documentation for a dataset")
    def document_dataset(path: str) -> str:
        return render_prompt("document-dataset", path)
