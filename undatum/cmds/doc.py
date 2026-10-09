"""Dataset documentation command module."""

import csv
import io
import json
import logging
import os
import re
import sys
from typing import Any

import yaml
from iterable.helpers.detect import detect_file_type

from ..ai import get_ai_service, get_structured_metadata
from ..common.command_utils import get_iterable_options, iter_command_rows
from ..common.s3_iterable import open_path as open_iterable
from ..common.schema_utils import duckdb_decompose
from ..common.tables import format_table
from ..constants import DUCKABLE_CODECS, DUCKABLE_FILE_TYPES, EU_DATA_THEMES
from ..utils import get_option, normalize_for_json
from .analyzer import OBJECTS_ANALYZE_LIMIT, analyze

logger = logging.getLogger(__name__)

DATA_THEME_URI_BY_LABEL = {theme["label"]: theme["uri"] for theme in EU_DATA_THEMES}


def _format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def _normalize_outtype(outtype: str) -> str:
    """Normalize output type alias to canonical name."""
    if not outtype:
        return "markdown"
    outtype = outtype.lower()
    if outtype in ["md", "markdown"]:
        return "markdown"
    if outtype in ["txt", "text"]:
        return "text"
    return outtype


def _build_title(filename: str) -> str:
    base = os.path.basename(filename)
    stem = os.path.splitext(base)[0]
    stem = re.sub(r"[_\-]+", " ", stem).strip()
    if not stem:
        return base
    return stem.title()


def _get_primary_fields(report) -> list[str]:
    if report.tables:
        return [field.name for field in report.tables[0].fields or []]
    return []


# Metadata extraction is delegated to iterabledata's shared implementation
# (``iterable.ai.metadata``) so undatum and the foundation stay in sync. The
# theme URIs and detection heuristics are identical, so output is unchanged.


def _extract_keywords(field_names: list[str], max_keywords: int = 15) -> list[str]:
    from iterable.ai.metadata import extract_keywords

    return extract_keywords(field_names, max_keywords=max_keywords)


def _extract_geographic_coverage(samples: list[Any], field_names: list[str]) -> dict[str, Any]:
    from iterable.ai.metadata import extract_geographic_coverage

    return extract_geographic_coverage(samples, field_names)


def _extract_temporal_coverage(samples: list[Any], field_names: list[str]) -> dict[str, Any] | None:
    from iterable.ai.metadata import extract_temporal_coverage

    return extract_temporal_coverage(samples, field_names)


def _detect_languages(samples: list[Any], field_names: list[str]) -> list[dict[str, Any]]:
    from iterable.ai.metadata import detect_languages

    return detect_languages(samples, field_names)


def _guess_data_theme(field_names: list[str], keywords: list[str]) -> dict[str, str] | None:
    from iterable.ai.metadata import classify_data_theme

    return classify_data_theme(field_names, keywords)


def _build_sample_csv(samples: list[Any], field_names: list[str]) -> str:
    if not samples:
        return ""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if field_names:
        writer.writerow(field_names)
    for sample in samples[:50]:
        if isinstance(sample, dict):
            row = [sample.get(name) for name in field_names]
        elif isinstance(sample, list):
            row = sample
        else:
            row = [sample]
        writer.writerow(row)
    return buffer.getvalue()


def _merge_ai_metadata(metadata: dict[str, Any], ai_metadata: dict[str, Any]) -> None:
    if not ai_metadata:
        return
    if isinstance(ai_metadata.get("keywords"), str):
        ai_metadata["keywords"] = [
            kw.strip() for kw in ai_metadata["keywords"].split(",") if kw.strip()
        ]
    if isinstance(ai_metadata.get("languages"), dict):
        ai_metadata["languages"] = [ai_metadata["languages"]]
    for key in (
        "title",
        "keywords",
        "geographic_coverage",
        "temporal_coverage",
        "languages",
        "data_theme",
    ):
        if ai_metadata.get(key) is not None:
            metadata[key] = ai_metadata[key]
    if ai_metadata.get("confidence") is not None:
        metadata["metadata_confidence"] = ai_metadata["confidence"]
    if ai_metadata.get("evidence") is not None:
        metadata["metadata_evidence"] = ai_metadata["evidence"]


# Metacrafter semantic-type scanning and parsing are delegated to iterabledata's
# shared implementation (``iterable.ai.semantic``). undatum keeps the
# report-coupled ``_apply_semantic_types`` below, which consumes these results.


def _parse_metacrafter_matches(entry: dict[str, Any]) -> list[dict[str, Any]]:
    from iterable.ai.semantic import _parse_metacrafter_matches as _parse

    return _parse(entry)


def _run_metacrafter_scan(filename: str) -> list[dict[str, Any]] | None:
    from iterable.ai.semantic import _run_metacrafter_scan as _scan

    return _scan(filename)


def _apply_semantic_types(report, metacrafter_entries: list[dict[str, Any]]) -> dict[str, Any]:
    pii_fields = []
    if not metacrafter_entries:
        return {"pii_fields": pii_fields}

    entry_map = {}
    for entry in metacrafter_entries:
        key = entry.get("key") or entry.get("name")
        if key:
            entry_map[key] = entry

    for table in report.tables or []:
        for field in table.fields or []:
            entry = entry_map.get(field.name)
            if not entry:
                field.semantic_types = []
                continue
            matches = _parse_metacrafter_matches(entry)
            field.semantic_types = matches
            if matches:
                field.sem_type = matches[0].get("type")
                field.sem_url = matches[0].get("url")
            tags = entry.get("tags") or []
            if isinstance(tags, str):
                tags = [tags]
            is_pii = any("pii" in str(tag).lower() for tag in tags)
            if is_pii:
                field.pii = True
            if is_pii or any("pii" in str(m.get("type", "")).lower() for m in matches):
                top_match = matches[0] if matches else {}
                pii_fields.append(
                    {
                        "field": field.name,
                        "type": top_match.get("type"),
                        "confidence": top_match.get("confidence"),
                    }
                )
    return {"pii_fields": pii_fields}


def _mask_samples(
    samples: list[Any], field_names: list[str], pii_fields: list[dict[str, Any]]
) -> list[Any]:
    from iterable.ai.semantic import mask_pii_samples

    return mask_pii_samples(samples, field_names, pii_fields)


def _build_stats(
    fromfile: str, filetype: str, compression: str, options: dict[str, Any]
) -> dict[str, Any] | None:
    """Build statistics summary using DuckDB when available."""
    if options.get("flatten_nested"):
        return None
    engine = get_option(options, "engine") or "auto"
    if engine not in ["auto", "duckdb"]:
        return None
    if filetype not in DUCKABLE_FILE_TYPES or compression not in DUCKABLE_CODECS:
        return None
    objects_limit = get_option(options, "objects_limit") or OBJECTS_ANALYZE_LIMIT
    columns_raw = duckdb_decompose(
        filename=fromfile, filetype=filetype, path="*", limit=objects_limit, use_summarize=True
    )
    fields = []
    for column in columns_raw:
        if len(column) < 6:
            continue
        try:
            unique_count = int(column[3])
        except (ValueError, TypeError):
            unique_count = 0
        try:
            total_count = int(column[4])
        except (ValueError, TypeError):
            total_count = 0
        try:
            uniq_share = float(column[5])
        except (ValueError, TypeError):
            uniq_share = 0.0
        fields.append(
            {
                "name": column[0],
                "type": column[1],
                "is_array": column[2] == "True" if isinstance(column[2], str) else bool(column[2]),
                "unique_count": unique_count,
                "total_count": total_count,
                "uniqueness_percent": uniq_share,
            }
        )
    return {"engine": "duckdb", "fields": fields}


def _build_samples(fromfile: str, options: dict[str, Any]) -> list[Any]:
    """Collect a bounded sample of records from the dataset."""
    sample_size = get_option(options, "sample_size")
    if sample_size is None:
        sample_size = 10
    if sample_size <= 0:
        return []
    iterableargs = get_iterable_options(options)
    samples = []
    try:
        iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
        try:
            for item in iter_command_rows(iterable, options):
                samples.append(normalize_for_json(item))
                if len(samples) >= sample_size:
                    break
        finally:
            iterable.close()
    except Exception as exc:
        logger.warning("doc: failed to sample records: %s", exc)
    return samples


def _build_doc_report(
    report,
    stats: dict[str, Any] | None,
    samples: list[Any],
    pii_fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assemble a documentation report from analysis results."""
    metadata = {
        "filename": report.filename,
        "file_size": report.file_size,
        "file_size_human": _format_file_size(report.file_size),
        "file_type": report.file_type,
        "compression": report.compression,
    }
    metadata.update(report.metadata or {})

    tables = []
    for table in report.tables or []:
        fields = []
        for field in table.fields or []:
            semantic_types = field.semantic_types or []
            if not semantic_types and field.sem_type:
                semantic_types = [
                    {"type": field.sem_type, "url": field.sem_url, "confidence": None}
                ]
            fields.append(
                {
                    "name": field.name,
                    "type": field.ftype,
                    "is_array": field.is_array,
                    "description": field.description,
                    "semantic_types": semantic_types,
                    "pii": field.pii,
                }
            )
        tables.append(
            {
                "id": table.id,
                "num_records": table.num_records,
                "num_cols": table.num_cols,
                "is_flat": table.is_flat,
                "description": table.description,
                "fields": fields,
            }
        )

    return {
        "metadata": metadata,
        "summary": {"total_tables": report.total_tables, "total_records": report.total_records},
        "schema": {"tables": tables},
        "statistics": stats,
        "samples": samples,
        "pii_fields": pii_fields or [],
    }


def _is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, (list, tuple, dict, set)) and not value:
        return True
    return False


def _format_markdown_inline(value: Any) -> str:
    if _is_empty_value(value):
        return "-"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            parts.append(f"{key}: {_format_markdown_inline(item)}")
        return "; ".join(parts) if parts else "-"
    if isinstance(value, (list, tuple, set)):
        items = [_format_markdown_inline(item) for item in value]
        items = [item for item in items if item]
        return ", ".join(items) if items else "-"
    return str(value)


def _format_markdown_value(value: Any) -> str:
    if _is_empty_value(value):
        return "-"
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            lines.append(f"  - {key}: {_format_markdown_inline(item)}")
        return "\n".join(lines) if lines else "-"
    return _format_markdown_inline(value)


def _render_markdown(doc: dict[str, Any]) -> str:
    """Render documentation in Markdown format."""
    lines = ["# Dataset Documentation", ""]

    lines.append("## Metadata")
    for key, value in doc["metadata"].items():
        if isinstance(value, dict) and not _is_empty_value(value):
            lines.append(f"- **{key}**:")
            lines.append(_format_markdown_value(value))
        else:
            lines.append(f"- **{key}**: {_format_markdown_value(value)}")
    lines.append("")

    lines.append("## Summary")
    summary_rows = [[key, value] for key, value in doc["summary"].items()]
    lines.append(format_table(summary_rows, ["Metric", "Value"], "github"))
    lines.append("")

    lines.append("## Schema")
    for table in doc["schema"]["tables"]:
        table_id = table["id"] or "table"
        lines.append(f"### Table: {table_id}")
        lines.append(f"- Records: {table['num_records']}")
        lines.append(f"- Columns: {table['num_cols']}")
        lines.append(f"- Flat: {'Yes' if table['is_flat'] else 'No'}")
        if table.get("description"):
            lines.append("")
            lines.append("Summary:")
            lines.append(table["description"])
        field_rows = []
        has_semantic = any(field.get("semantic_types") for field in table["fields"])
        has_pii = any(field.get("pii") for field in table["fields"])
        headers = ["Field", "Type", "Array", "Description"]
        if has_semantic:
            headers.append("Semantic Types")
        if has_pii:
            headers.append("PII")
        for field in table["fields"]:
            row = [
                field["name"],
                field["type"],
                "Yes" if field["is_array"] else "No",
                field.get("description") or "-",
            ]
            if has_semantic:
                semantic_types = [
                    item.get("type") for item in field.get("semantic_types", []) if item.get("type")
                ]
                row.append(", ".join(semantic_types) if semantic_types else "-")
            if has_pii:
                row.append("Yes" if field.get("pii") else "No")
            field_rows.append(row)
        if field_rows:
            lines.append("")
            lines.append(format_table(field_rows, headers, "github"))
        lines.append("")

    if doc.get("statistics"):
        lines.append("## Statistics")
        stat_rows = []
        for field in doc["statistics"].get("fields", []):
            stat_rows.append(
                [
                    field["name"],
                    field["unique_count"],
                    field["total_count"],
                    f"{field['uniqueness_percent']:.2f}",
                ]
            )
        if stat_rows:
            lines.append(
                format_table(stat_rows, ["Field", "Unique", "Total", "Unique %"], "github")
            )
        else:
            lines.append("No statistics available.")
        lines.append("")

    if doc.get("pii_fields"):
        lines.append("## PII Summary")
        pii_rows = []
        for item in doc.get("pii_fields", []):
            pii_rows.append(
                [
                    item.get("field"),
                    item.get("type") or "-",
                    item.get("confidence") if item.get("confidence") is not None else "-",
                ]
            )
        if pii_rows:
            lines.append(format_table(pii_rows, ["Field", "Type", "Confidence"], "github"))
        else:
            lines.append("No PII fields detected.")
        lines.append("")

    if doc["samples"]:
        lines.append("## Samples")
        lines.append("```json")
        lines.append(json.dumps(doc["samples"], indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")

    return "\n".join(lines)


def _render_text(doc: dict[str, Any]) -> str:
    """Render documentation in plain text format."""
    lines = []
    lines.append("DATASET DOCUMENTATION")
    lines.append("=" * 70)
    lines.append("")

    lines.append("Metadata")
    lines.append("-" * 70)
    meta_rows = [[key, value] for key, value in doc["metadata"].items()]
    lines.append(format_table(meta_rows, ["Attribute", "Value"], "grid"))
    lines.append("")

    lines.append("Summary")
    lines.append("-" * 70)
    summary_rows = [[key, value] for key, value in doc["summary"].items()]
    lines.append(format_table(summary_rows, ["Metric", "Value"], "grid"))
    lines.append("")

    lines.append("Schema")
    lines.append("-" * 70)
    for table in doc["schema"]["tables"]:
        table_id = table["id"] or "table"
        lines.append(f"Table: {table_id}")
        lines.append(f"  Records: {table['num_records']}")
        lines.append(f"  Columns: {table['num_cols']}")
        lines.append(f"  Flat: {'Yes' if table['is_flat'] else 'No'}")
        if table.get("description"):
            lines.append("  Summary:")
            lines.append(f"  {table['description']}")
        field_rows = []
        has_semantic = any(field.get("semantic_types") for field in table["fields"])
        has_pii = any(field.get("pii") for field in table["fields"])
        headers = ["Field", "Type", "Array", "Description"]
        if has_semantic:
            headers.append("Semantic Types")
        if has_pii:
            headers.append("PII")
        for field in table["fields"]:
            row = [
                field["name"],
                field["type"],
                "Yes" if field["is_array"] else "No",
                field.get("description") or "-",
            ]
            if has_semantic:
                semantic_types = [
                    item.get("type") for item in field.get("semantic_types", []) if item.get("type")
                ]
                row.append(", ".join(semantic_types) if semantic_types else "-")
            if has_pii:
                row.append("Yes" if field.get("pii") else "No")
            field_rows.append(row)
        if field_rows:
            lines.append(format_table(field_rows, headers, "grid"))
        lines.append("")

    if doc.get("statistics"):
        lines.append("Statistics")
        lines.append("-" * 70)
        stat_rows = []
        for field in doc["statistics"].get("fields", []):
            stat_rows.append(
                [
                    field["name"],
                    field["unique_count"],
                    field["total_count"],
                    f"{field['uniqueness_percent']:.2f}",
                ]
            )
        if stat_rows:
            lines.append(format_table(stat_rows, ["Field", "Unique", "Total", "Unique %"], "grid"))
        else:
            lines.append("No statistics available.")
        lines.append("")

    if doc.get("pii_fields"):
        lines.append("PII Summary")
        lines.append("-" * 70)
        pii_rows = []
        for item in doc.get("pii_fields", []):
            pii_rows.append(
                [
                    item.get("field"),
                    item.get("type") or "-",
                    item.get("confidence") if item.get("confidence") is not None else "-",
                ]
            )
        if pii_rows:
            lines.append(format_table(pii_rows, ["Field", "Type", "Confidence"], "grid"))
        else:
            lines.append("No PII fields detected.")
        lines.append("")

    if doc["samples"]:
        lines.append("Samples")
        lines.append("-" * 70)
        lines.append(json.dumps(doc["samples"], indent=2, ensure_ascii=False))
        lines.append("")

    return "\n".join(lines)


def _write_doc_output(doc: dict[str, Any], outtype: str, output_stream) -> None:
    """Write documentation to output stream in the specified format."""
    if outtype == "json":
        output_stream.write(json.dumps(doc, indent=2, ensure_ascii=False))
        output_stream.write("\n")
        return
    if outtype == "yaml":
        output_stream.write(yaml.dump(doc, Dumper=yaml.Dumper))
        return
    if outtype == "text":
        output_stream.write(_render_text(doc))
        return
    output_stream.write(_render_markdown(doc))


class Documenter:
    """Dataset documentation command handler."""

    def __init__(self):
        pass

    def document(self, fromfile: str, options: dict[str, Any] | None = None) -> None:
        """Generate dataset documentation in multiple formats."""
        if options is None:
            options = {}
        logger.debug("doc: start processing %s", fromfile)

        outtype = _normalize_outtype(get_option(options, "format") or "markdown")
        output_file = get_option(options, "output")
        logger.debug("doc: output format=%s output_file=%s", outtype, output_file or "stdout")

        format_in = get_option(options, "format_in")
        filetype = format_in
        compression = "raw"
        if filetype is None:
            logger.debug("doc: detecting input file type")
            ftype = detect_file_type(fromfile)
            if ftype["success"]:
                filetype = ftype["datatype"].id()
                if ftype["codec"] is not None:
                    compression = ftype["codec"].id()
        logger.debug("doc: input type=%s compression=%s", filetype, compression)

        encoding = get_option(options, "encoding")
        objects_limit = get_option(options, "objects_limit") or OBJECTS_ANALYZE_LIMIT
        logger.debug(
            "doc: analyze options encoding=%s objects_limit=%s autodoc=%s",
            encoding,
            objects_limit,
            options.get("autodoc", False),
        )

        logger.debug("doc: running analyzer")
        report = analyze(
            fromfile,
            filetype=filetype,
            compression=compression,
            objects_limit=objects_limit,
            encoding=encoding,
            autodoc=options.get("autodoc", False),
            lang=options.get("lang", "English"),
            ai_provider=options.get("ai_provider"),
            ai_config=options.get("ai_config"),
            table_name=options.get("table"),
            start_page=options.get("start_page") or 0,
            trust=bool(options.get("trust")),
            engine=get_option(options, "engine") or "auto",
            delimiter=options.get("delimiter"),
            options=options,
        )
        logger.debug(
            "doc: analysis complete tables=%s records=%s", report.total_tables, report.total_records
        )

        logger.debug("doc: building statistics")
        stats = _build_stats(fromfile, report.file_type, report.compression, options)
        if stats:
            logger.debug(
                "doc: statistics engine=%s fields=%s",
                stats.get("engine"),
                len(stats.get("fields", [])),
            )
        else:
            logger.debug("doc: statistics skipped (not available)")

        logger.debug("doc: collecting samples")
        samples = _build_samples(fromfile, options)
        logger.debug("doc: samples collected=%s", len(samples))
        field_names = _get_primary_fields(report)
        metadata = report.metadata or {}
        metadata.setdefault("title", _build_title(report.filename))
        keywords = _extract_keywords(field_names)
        metadata.setdefault("keywords", keywords)
        metadata.setdefault(
            "geographic_coverage", _extract_geographic_coverage(samples, field_names)
        )
        metadata.setdefault("temporal_coverage", _extract_temporal_coverage(samples, field_names))
        metadata.setdefault("languages", _detect_languages(samples, field_names))
        metadata.setdefault("data_theme", _guess_data_theme(field_names, keywords))
        report.metadata = metadata
        logger.debug(
            "doc: metadata assembled fields=%s keywords=%s", len(field_names), len(keywords)
        )

        if options.get("autodoc"):
            try:
                logger.debug("doc: generating AI metadata")
                ai_config = options.get("ai_config") or {}
                ai_service = get_ai_service(provider=options.get("ai_provider"), config=ai_config)
                sample_csv = _build_sample_csv(samples, field_names)
                if sample_csv:
                    ai_metadata = get_structured_metadata(
                        sample_csv,
                        field_names,
                        language=options.get("lang", "English"),
                        ai_service=ai_service,
                    )
                    if ai_metadata and isinstance(ai_metadata.get("data_theme"), dict):
                        label = ai_metadata["data_theme"].get("label")
                        if label in DATA_THEME_URI_BY_LABEL and not ai_metadata["data_theme"].get(
                            "uri"
                        ):
                            ai_metadata["data_theme"]["uri"] = DATA_THEME_URI_BY_LABEL.get(label)
                        if label not in DATA_THEME_URI_BY_LABEL:
                            ai_metadata["data_theme"] = None
                    _merge_ai_metadata(metadata, ai_metadata)
                else:
                    logger.debug("doc: AI metadata skipped (no sample CSV)")
            except Exception as exc:
                logger.warning("doc: failed to generate AI metadata: %s", exc)

        pii_fields = []
        if options.get("semantic_types") or options.get("pii_detect"):
            logger.debug("doc: running metacrafter scan")
            entries = _run_metacrafter_scan(fromfile)
            if entries:
                pii_fields = _apply_semantic_types(report, entries).get("pii_fields", [])
                logger.debug(
                    "doc: metacrafter entries=%s pii_fields=%s", len(entries), len(pii_fields)
                )
            else:
                logger.warning("doc: metacrafter not available or returned no results")
                for table in report.tables or []:
                    for field in table.fields or []:
                        field.semantic_types = []
        if options.get("pii_mask_samples") and pii_fields:
            logger.debug("doc: masking samples for PII fields")
            samples = _mask_samples(samples, field_names, pii_fields)

        logger.debug("doc: assembling report")
        doc_report = _build_doc_report(report, stats, samples, pii_fields)

        if output_file:
            logger.debug("doc: writing output to file")
            with open(output_file, "w", encoding="utf8") as output_stream:
                _write_doc_output(doc_report, outtype, output_stream)
        else:
            logger.debug("doc: writing output to stdout")
            _write_doc_output(doc_report, outtype, sys.stdout)
        logger.debug("doc: finished")
