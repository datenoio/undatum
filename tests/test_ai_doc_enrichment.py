"""Tests for AI doc enrichment helpers."""

import json

from undatum.ai.doc_enrichment import (
    build_field_hints,
    enrich_schema_fields,
    hint_from_field_name,
    match_llm_field_name,
    prepare_doc_source,
    restore_source_filename,
)


def test_hint_from_sdmx_field_name():
    assert hint_from_field_name("FREQ:Frequency") == "Frequency"
    assert hint_from_field_name("\ufeffDATAFLOW_ID:Dataflow ID") == "Dataflow ID"
    assert hint_from_field_name("Unit") is None


def test_match_llm_field_name_sdmx_aliases():
    known = ["FREQ:Frequency", "REF_AREA:Reference area", "Unit"]
    assert match_llm_field_name("FREQ", known) == "FREQ:Frequency"
    assert match_llm_field_name("Frequency", known) == "FREQ:Frequency"
    assert match_llm_field_name("Reference area", known) == "REF_AREA:Reference area"


def test_match_llm_field_name_strips_bom():
    known = ["\ufeffDATAFLOW_ID:Dataflow ID", "Unit"]
    assert match_llm_field_name("DATAFLOW_ID:Dataflow ID", known) == "\ufeffDATAFLOW_ID:Dataflow ID"


def test_enrich_schema_fields_fills_missing_descriptions():
    known = ["FREQ:Frequency", "Unit"]
    fields = [
        {"name": "FREQ", "type": "string", "description": "Reporting frequency"},
        {"name": "Unit", "type": "string"},
    ]
    enriched = enrich_schema_fields(fields, known, build_field_hints(known))
    by_name = {f["name"]: f for f in enriched}
    assert by_name["FREQ:Frequency"]["description"] == "Reporting frequency"
    assert not by_name["Unit"].get("description")


def test_restore_source_filename_replaces_temp_name():
    result = {
        "source": {"name": "undatum-doc-abc123.jsonl"},
        "blocks": {
            "general": {
                "data": {"file_name": "undatum-doc-abc123.jsonl", "title": "Dataset"},
                "markdown": "## General\n\n| Property | Value |\n| undatum-doc-abc123.jsonl |",
            },
            "examples": {
                "markdown": "read_json_auto('undatum-doc-abc123.jsonl')",
            },
        },
        "full_document_markdown": "# Doc\n\nundatum-doc-abc123.jsonl",
    }
    restore_source_filename(
        result,
        "/path/to/data.jsonl",
        "/tmp/undatum-doc-abc123.jsonl",
    )
    assert result["source"]["name"] == "data.jsonl"
    assert result["blocks"]["general"]["data"]["file_name"] == "data.jsonl"
    assert "data.jsonl" in result["blocks"]["general"]["markdown"]
    assert "undatum-doc-abc123.jsonl" not in result["full_document_markdown"]


def test_prepare_doc_source_strips_bom_from_jsonl(tmp_path):
    path = tmp_path / "data.jsonl"
    path.write_text(
        json.dumps({"\ufeffDATAFLOW_ID:Dataflow ID": "x", "Unit": "AED"}) + "\n",
        encoding="utf-8",
    )
    doc_path, cleanup, hints, field_names = prepare_doc_source(str(path))
    try:
        assert "\ufeff" not in field_names[0]
        assert hints["DATAFLOW_ID:Dataflow ID"] == "Dataflow ID"
        with open(doc_path, encoding="utf-8") as handle:
            row = json.loads(handle.readline())
        assert "\ufeffDATAFLOW_ID:Dataflow ID" not in row
        assert "DATAFLOW_ID:Dataflow ID" in row
    finally:
        cleanup()
