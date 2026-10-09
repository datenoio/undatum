"""Helpers for ``undatum ai doc`` — input normalization and schema description enrichment."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable
from typing import Any


def _strip_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def field_aliases(name: str) -> set[str]:
    """Return normalized aliases for matching LLM field names to schema names."""
    clean = _strip_bom(name).strip()
    aliases = {clean, clean.lower()}
    if ":" in clean:
        code, _, label = clean.partition(":")
        code = code.strip()
        label = label.strip()
        for part in (code, label):
            if part:
                aliases.add(part)
                aliases.add(part.lower())
    return aliases


def hint_from_field_name(name: str) -> str | None:
    """Derive a fallback description from SDMX-style ``CODE:Label`` column names."""
    clean = _strip_bom(name).strip()
    if ":" in clean:
        _, _, label = clean.partition(":")
        label = label.strip()
        return label or None
    if " " in clean:
        return clean
    return None


def match_llm_field_name(llm_name: str, known_names: list[str]) -> str | None:
    """Map an LLM-returned field name onto the canonical schema field name."""
    if not llm_name:
        return None
    llm_clean = _strip_bom(str(llm_name)).strip()
    llm_aliases = field_aliases(llm_clean)
    for known in known_names:
        known_clean = _strip_bom(known).strip()
        if llm_clean == known_clean:
            return known
        if llm_aliases & field_aliases(known_clean):
            return known
    return None


def _jsonl_needs_key_normalization(path: str) -> bool:
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                return False
            if not isinstance(row, dict):
                return False
            return any(_strip_bom(key) != key for key in row)
    return False


def _rewrite_jsonl_keys(path: str) -> str:
    """Write a copy of a JSONL file with BOM stripped from object keys."""
    fd, temp_path = tempfile.mkstemp(suffix=".jsonl", prefix="undatum-doc-")
    os.close(fd)
    with open(path, encoding="utf-8") as src, open(temp_path, "w", encoding="utf-8") as dst:
        for line in src:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                row = {_strip_bom(key): value for key, value in row.items()}
            dst.write(json.dumps(row, ensure_ascii=False) + "\n")
    return temp_path


def build_field_hints(field_names: list[str]) -> dict[str, str]:
    """Build fallback descriptions from column naming conventions."""
    hints: dict[str, str] = {}
    for name in field_names:
        hint = hint_from_field_name(name)
        if hint:
            hints[_strip_bom(name)] = hint
    return hints


def prepare_doc_source(filename: str) -> tuple[str, Callable[[], None], dict[str, str], list[str]]:
    """Normalize a file for documentation and return fallback field hints.

    Returns:
        Tuple of (path to use, cleanup callback, field-name hint map, canonical field names).
    """

    def cleanup() -> None:
        return None

    path = filename
    hints: dict[str, str] = {}
    field_names: list[str] = []

    lower = filename.lower()
    if lower.endswith(".jsonl") or lower.endswith(".ndjson"):
        if _jsonl_needs_key_normalization(filename):
            path = _rewrite_jsonl_keys(filename)

            def cleanup(p: str = path) -> None:
                if os.path.exists(p):
                    os.remove(p)

    try:
        from iterable.ops import schema as schema_ops

        schema_info = schema_ops.infer(path, detect_constraints=False)
        field_names = list(schema_info.get("fields", {}).keys())
        hints = build_field_hints(field_names)
    except Exception:
        # Best effort: never fail the command because of this step.
        logging.getLogger(__name__).debug(
            "optional documentation enrichment step failed", exc_info=True
        )

    return path, cleanup, hints, field_names


def enrich_schema_fields(
    fields: list[dict[str, Any]],
    known_names: list[str],
    hints: dict[str, str],
) -> list[dict[str, Any]]:
    """Fill missing schema descriptions and remap LLM field names to canonical names."""
    by_canonical: dict[str, dict[str, Any]] = {}

    for item in fields:
        if not isinstance(item, dict):
            continue
        raw_name = item.get("name")
        if not raw_name:
            continue
        canonical = match_llm_field_name(str(raw_name), known_names) or _strip_bom(str(raw_name))
        existing = by_canonical.get(canonical)
        if existing is None or (not existing.get("description") and item.get("description")):
            merged = dict(item)
            merged["name"] = canonical
            by_canonical[canonical] = merged

    ordered: list[dict[str, Any]] = []
    for name in known_names:
        canonical = _strip_bom(name)
        if canonical in by_canonical:
            field = by_canonical.pop(canonical)
        else:
            field = {"name": name}
        if not field.get("description"):
            field["description"] = (
                hints.get(canonical) or hints.get(name) or hint_from_field_name(name)
            )
        ordered.append(field)

    ordered.extend(by_canonical.values())
    return ordered


def restore_source_filename(
    result: dict[str, Any],
    original_path: str,
    processed_path: str | None = None,
) -> None:
    """Replace temp/processed paths in doc output with the user's original file name."""
    original_name = os.path.basename(original_path)
    processed_name = os.path.basename(processed_path) if processed_path else None
    if not processed_name or processed_name == original_name:
        return

    if isinstance(result.get("source"), dict):
        result["source"]["name"] = original_name

    blocks = result.get("blocks") or {}
    general = blocks.get("general")
    if isinstance(general, dict):
        data = general.get("data") or {}
        data["file_name"] = original_name
        general["data"] = data
        language = data.get("language") or "English"
        try:
            from iterable.ai import blocks as blocks_module

            general["markdown"] = blocks_module._render_general_md(data, language)
        except Exception:
            md = general.get("markdown")
            if isinstance(md, str):
                general["markdown"] = md.replace(processed_name, original_name)

    for block in blocks.values():
        if not isinstance(block, dict):
            continue
        md = block.get("markdown")
        if isinstance(md, str) and processed_name in md:
            block["markdown"] = md.replace(processed_name, original_name)

    full = result.get("full_document_markdown")
    if isinstance(full, str) and processed_name in full:
        result["full_document_markdown"] = full.replace(processed_name, original_name)


def enrich_blocks_result(
    result: dict[str, Any],
    hints: dict[str, str],
    known_names: list[str] | None = None,
    requested_blocks: list[str] | None = None,
) -> None:
    """Post-process block output to ensure every schema field has a description."""
    blocks = result.get("blocks") or {}
    schema_block = blocks.get("schema")
    if not schema_block:
        return

    data = schema_block.get("data") or {}
    fields = data.get("fields") or []
    if not fields and not known_names:
        return

    canonical_names = known_names or [
        str(f.get("name")) for f in fields if isinstance(f, dict) and f.get("name")
    ]
    if not canonical_names:
        return

    enriched = enrich_schema_fields(fields, canonical_names, hints)
    data["fields"] = enriched
    schema_block["data"] = data

    language = (
        (blocks.get("general") or {}).get("data", {}).get("language")
        or result.get("language")
        or "English"
    )
    try:
        from iterable.ai import blocks as blocks_module

        schema_block["markdown"] = blocks_module._render_schema_md(enriched, language)
    except Exception:
        # Best effort: never fail the command because of this step.
        logging.getLogger(__name__).debug(
            "optional documentation enrichment step failed", exc_info=True
        )

    if not requested_blocks:
        return
    try:
        from iterable.ai.blocks import BlockContext
        from iterable.ai.doc import _assemble_markdown, _ordered_block_keys

        ctx = BlockContext(language=language)
        keys = _ordered_block_keys(blocks, requested_blocks)
        subset = {k: blocks[k] for k in keys if k in blocks}
        result["full_document_markdown"] = _assemble_markdown(ctx, subset, requested_blocks, None)
    except Exception:
        # Best effort: never fail the command because of this step.
        logging.getLogger(__name__).debug(
            "optional documentation enrichment step failed", exc_info=True
        )
