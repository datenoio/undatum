"""Diff command module - compare two files and show differences."""

import csv
import json
import logging
import sys
from io import StringIO
from typing import Any

from ..common.command_utils import (
    ITERABLE_OPTIONS_KEYS,  # noqa: F401
    get_side_iterable_options,
    iter_command_rows,
)
from ..common.s3_iterable import open_path as open_iterable
from ..utils import field_values, get_option, normalize_for_json

logger = logging.getLogger(__name__)

DETAIL_LIMIT = 100


def _normalize_key_value(value, ignore_case):
    if isinstance(value, str) and ignore_case:
        return value.lower()
    return value


def _get_key_value(item, key_fields, ignore_case):
    """Get key value for comparison."""
    if not key_fields:
        # Use all fields as key
        return tuple(
            sorted(
                (k, _normalize_key_value(v, ignore_case)) for k, v in item.items() if v is not None
            )
        )
    values = []
    for field in key_fields:
        found = field_values(item, field)
        values.append(_normalize_key_value(found[0] if found else None, ignore_case))
    return tuple(values)


def _coerce_numeric(value):
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _values_equal(value1, value2, numeric_tolerance, ignore_case):
    if numeric_tolerance is not None:
        num1 = _coerce_numeric(value1)
        num2 = _coerce_numeric(value2)
        if num1 is not None and num2 is not None:
            return abs(num1 - num2) <= numeric_tolerance

    if isinstance(value1, str) and isinstance(value2, str) and ignore_case:
        return value1.lower() == value2.lower()

    if isinstance(value1, dict) and isinstance(value2, dict):
        if set(value1.keys()) != set(value2.keys()):
            return False
        return all(
            _values_equal(value1[key], value2[key], numeric_tolerance, ignore_case)
            for key in value1.keys()
        )

    if isinstance(value1, (list, tuple)) and isinstance(value2, (list, tuple)):
        if len(value1) != len(value2):
            return False
        return all(
            _values_equal(v1, v2, numeric_tolerance, ignore_case)
            for v1, v2 in zip(value1, value2, strict=False)
        )

    return value1 == value2


def _records_equal(record1, record2, numeric_tolerance, ignore_case):
    if not isinstance(record1, dict) or not isinstance(record2, dict):
        return _values_equal(record1, record2, numeric_tolerance, ignore_case)
    if set(record1.keys()) != set(record2.keys()):
        return False
    return all(
        _values_equal(record1[key], record2[key], numeric_tolerance, ignore_case)
        for key in record1.keys()
    )


def _normalize_value_for_signature(value, ignore_case, numeric_tolerance):
    if isinstance(value, dict):
        return {
            k: _normalize_value_for_signature(v, ignore_case, numeric_tolerance)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_normalize_value_for_signature(v, ignore_case, numeric_tolerance) for v in value]
    if isinstance(value, str):
        if ignore_case:
            value = value.lower()
        if numeric_tolerance is not None:
            numeric = _coerce_numeric(value)
            if numeric is not None:
                return round(numeric / numeric_tolerance)
        return value
    if isinstance(value, (int, float)):
        if numeric_tolerance is not None:
            return round(float(value) / numeric_tolerance)
        return float(value)
    return value


def _record_signature(record, ignore_case, numeric_tolerance):
    normalized = _normalize_value_for_signature(record, ignore_case, numeric_tolerance)
    return json.dumps(normalized, sort_keys=True, default=str)


def _format_summary(summary):
    return (
        "Summary: "
        f"file1={summary['file1_count']}, "
        f"file2={summary['file2_count']}, "
        f"added={summary['added_count']}, "
        f"removed={summary['removed_count']}, "
        f"changed={summary['changed_count']}"
    )


def _format_detailed_csv(added, removed, changed):
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["change_type", "key", "old", "new"])
    writer.writeheader()

    for item in added:
        writer.writerow(
            {
                "change_type": "added",
                "key": "",
                "old": "",
                "new": json.dumps(normalize_for_json(item), default=str),
            }
        )
    for item in removed:
        writer.writerow(
            {
                "change_type": "removed",
                "key": "",
                "old": json.dumps(normalize_for_json(item), default=str),
                "new": "",
            }
        )
    for change in changed:
        writer.writerow(
            {
                "change_type": "changed",
                "key": json.dumps(normalize_for_json(change["key"]), default=str),
                "old": json.dumps(normalize_for_json(change["old"]), default=str),
                "new": json.dumps(normalize_for_json(change["new"]), default=str),
            }
        )

    return buffer.getvalue().rstrip("\n")


def _format_detailed_markdown(result):
    lines = [
        "# Diff Report",
        "",
        "## Summary",
        f"- File 1 rows: {result['summary']['file1_count']}",
        f"- File 2 rows: {result['summary']['file2_count']}",
        f"- Added rows: {result['summary']['added_count']}",
        f"- Removed rows: {result['summary']['removed_count']}",
        f"- Changed rows: {result['summary']['changed_count']}",
    ]
    if result["added"]:
        lines.append("")
        lines.append("## Added (first 100)")
        for item in result["added"][:DETAIL_LIMIT]:
            lines.append(f"- `{json.dumps(normalize_for_json(item), default=str)}`")
    if result["removed"]:
        lines.append("")
        lines.append("## Removed (first 100)")
        for item in result["removed"][:DETAIL_LIMIT]:
            lines.append(f"- `{json.dumps(normalize_for_json(item), default=str)}`")
    if result["changed"]:
        lines.append("")
        lines.append("## Changed (first 100)")
        for change in result["changed"][:DETAIL_LIMIT]:
            lines.append(f"- Key: `{json.dumps(normalize_for_json(change['key']), default=str)}`")
            lines.append(f"  - Old: `{json.dumps(normalize_for_json(change['old']), default=str)}`")
            lines.append(f"  - New: `{json.dumps(normalize_for_json(change['new']), default=str)}`")
    return "\n".join(lines)


def _format_detailed_html(result):
    lines = [
        "<html>",
        "<head><title>Diff Report</title></head>",
        "<body>",
        "<h1>Diff Report</h1>",
        "<h2>Summary</h2>",
        "<ul>",
        f"<li>File 1 rows: {result['summary']['file1_count']}</li>",
        f"<li>File 2 rows: {result['summary']['file2_count']}</li>",
        f"<li>Added rows: {result['summary']['added_count']}</li>",
        f"<li>Removed rows: {result['summary']['removed_count']}</li>",
        f"<li>Changed rows: {result['summary']['changed_count']}</li>",
        "</ul>",
    ]
    if result["added"]:
        lines.append("<h2>Added (first 100)</h2><pre>")
        for item in result["added"][:DETAIL_LIMIT]:
            lines.append(json.dumps(normalize_for_json(item), default=str))
        lines.append("</pre>")
    if result["removed"]:
        lines.append("<h2>Removed (first 100)</h2><pre>")
        for item in result["removed"][:DETAIL_LIMIT]:
            lines.append(json.dumps(normalize_for_json(item), default=str))
        lines.append("</pre>")
    if result["changed"]:
        lines.append("<h2>Changed (first 100)</h2><pre>")
        for change in result["changed"][:DETAIL_LIMIT]:
            lines.append(f"Key: {json.dumps(normalize_for_json(change['key']), default=str)}")
            lines.append(f"Old: {json.dumps(normalize_for_json(change['old']), default=str)}")
            lines.append(f"New: {json.dumps(normalize_for_json(change['new']), default=str)}")
            lines.append("")
        lines.append("</pre>")
    lines.append("</body></html>")
    return "\n".join(lines)


def compare_files(file1: str, file2: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Records added, removed and changed between two files.

    Args:
        file1: Old file.
        file2: New file.
        options: ``key`` (comma-separated key fields), ``ignore_order``, ``ignore_case``,
            ``numeric_tolerance`` and reader options (``*2`` for the second file).

    Returns:
        ``added``, ``removed``, ``changed`` (``{key, old, new}``), ``key`` and ``summary``.
    """
    options = options or {}
    key_fields = get_option(options, "key")
    ignore_order = bool(get_option(options, "ignore_order"))
    numeric_tolerance = get_option(options, "numeric_tolerance")
    ignore_case = bool(get_option(options, "ignore_case"))

    key_field_list = None
    if key_fields:
        key_field_list = [f.strip() for f in key_fields.split(",")]

    iterableargs1 = get_side_iterable_options(options, 1)
    iterableargs2 = get_side_iterable_options(options, 2)

    # Load file1 into dictionary by key
    iterable1 = open_iterable(file1, mode="r", iterableargs=iterableargs1)
    file1_items = {}
    file1_rows = []

    try:
        count1 = 0
        for item in iter_command_rows(iterable1, options):
            count1 += 1
            if isinstance(item, dict):
                file1_rows.append(item)
                if key_field_list:
                    key = _get_key_value(item, key_field_list, ignore_case)
                    file1_items[key] = item
    finally:
        iterable1.close()

    # Load file2 into dictionary by key
    iterable2 = open_iterable(file2, mode="r", iterableargs=iterableargs2)
    file2_items = {}
    file2_rows = []

    try:
        count2 = 0
        for item in iter_command_rows(iterable2, options):
            count2 += 1
            if isinstance(item, dict):
                file2_rows.append(item)
                if key_field_list:
                    key = _get_key_value(item, key_field_list, ignore_case)
                    file2_items[key] = item
    finally:
        iterable2.close()

    # Find differences
    added = []  # In file2 but not in file1
    removed = []  # In file1 but not in file2
    changed = []  # Same key but different values

    if key_field_list:
        for key, item2 in file2_items.items():
            if key not in file1_items:
                added.append(item2)
            else:
                item1 = file1_items[key]
                if not _records_equal(item1, item2, numeric_tolerance, ignore_case):
                    changed.append({"key": key, "old": item1, "new": item2})

        for key, item1 in file1_items.items():
            if key not in file2_items:
                removed.append(item1)
    elif ignore_order:
        file1_counts = {}
        file1_examples = {}
        for item in file1_rows:
            signature = _record_signature(item, ignore_case, numeric_tolerance)
            file1_counts[signature] = file1_counts.get(signature, 0) + 1
            if signature not in file1_examples:
                file1_examples[signature] = item
        file2_counts = {}
        file2_examples = {}
        for item in file2_rows:
            signature = _record_signature(item, ignore_case, numeric_tolerance)
            file2_counts[signature] = file2_counts.get(signature, 0) + 1
            if signature not in file2_examples:
                file2_examples[signature] = item

        for signature, count in file2_counts.items():
            diff = count - file1_counts.get(signature, 0)
            if diff > 0:
                added.extend([file2_examples[signature]] * diff)
        for signature, count in file1_counts.items():
            diff = count - file2_counts.get(signature, 0)
            if diff > 0:
                removed.extend([file1_examples[signature]] * diff)
    else:
        min_len = min(len(file1_rows), len(file2_rows))
        for index in range(min_len):
            item1 = file1_rows[index]
            item2 = file2_rows[index]
            if not _records_equal(item1, item2, numeric_tolerance, ignore_case):
                changed.append({"key": index, "old": item1, "new": item2})
        if len(file2_rows) > min_len:
            added.extend(file2_rows[min_len:])
        if len(file1_rows) > min_len:
            removed.extend(file1_rows[min_len:])

    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "key": key_field_list,
        "summary": {
            "file1_count": count1,
            "file2_count": count2,
            "added_count": len(added),
            "removed_count": len(removed),
            "changed_count": len(changed),
        },
    }


class Differ:
    """Differ command handler - compare two files."""

    def __init__(self):
        pass

    def diff(self, file1, file2, options=None):
        """Compare two files and show differences."""
        if options is None:
            options = {}
        logger.debug("Comparing %s and %s", file1, file2)

        format_type = get_option(options, "format")
        output_format = get_option(options, "output_format")
        to_file = get_option(options, "output")
        summary_only = bool(get_option(options, "summary_only"))
        max_added_rows = get_option(options, "max_added_rows")
        max_removed_rows = get_option(options, "max_removed_rows")
        max_changed_rows = get_option(options, "max_changed_rows")

        result = compare_files(file1, file2, options)
        added, removed, changed = result["added"], result["removed"], result["changed"]
        key_field_list = result.pop("key")
        count1 = result["summary"]["file1_count"]
        count2 = result["summary"]["file2_count"]

        detailed_format = output_format or format_type
        if detailed_format is None and to_file:
            detailed_format = "json"

        # JSON on stdout is one document: the summary line goes to stderr then.
        json_stdout = detailed_format == "json" and not to_file
        summary_text = _format_summary(result["summary"])
        print(summary_text, file=sys.stderr if json_stdout else sys.stdout)

        output_text = None
        if detailed_format == "json":
            from ..common.results import DIFF, dumps, envelope

            document = {"file1": file1, "file2": file2, "key": key_field_list}
            document["summary"] = result["summary"]
            if not summary_only:
                document.update(added=added, removed=removed, changed=changed)
            output_text = dumps(envelope(DIFF, document))
            if to_file:
                with open(to_file, "w", encoding="utf8") as out:
                    out.write(output_text + "\n")
            else:
                print(output_text)
        elif not summary_only and detailed_format:
            if detailed_format == "unified":
                lines = []
                lines.append(f"--- {file1}")
                lines.append(f"+++ {file2}")
                lines.append("@@ Summary @@")
                lines.append(f"- Removed: {len(removed)}")
                lines.append(f"+ Added: {len(added)}")
                lines.append(f"~ Changed: {len(changed)}")
                if removed:
                    lines.append("\n=== Removed ===")
                    for item in removed[:10]:
                        lines.append(f"- {item}")
                if added:
                    lines.append("\n=== Added ===")
                    for item in added[:10]:
                        lines.append(f"+ {item}")
                if changed:
                    lines.append("\n=== Changed ===")
                    for change in changed[:10]:
                        lines.append(f"~ {change['key']}")
                        lines.append(f"  Old: {change['old']}")
                        lines.append(f"  New: {change['new']}")
                output_text = "\n".join(lines)
            elif detailed_format == "csv":
                output_text = _format_detailed_csv(added, removed, changed)
            elif detailed_format == "markdown":
                output_text = _format_detailed_markdown(result)
            elif detailed_format == "html":
                output_text = _format_detailed_html(result)
            else:
                raise ValueError(f"Unsupported output format: {detailed_format}")

            if to_file:
                out = open(to_file, "w", encoding="utf8")
                out.write(output_text)
                out.write("\n")
                out.close()
            else:
                print(output_text)

        threshold_exceeded = False
        if max_added_rows is not None and len(added) > max_added_rows:
            threshold_exceeded = True
        if max_removed_rows is not None and len(removed) > max_removed_rows:
            threshold_exceeded = True
        if max_changed_rows is not None and len(changed) > max_changed_rows:
            threshold_exceeded = True
        if threshold_exceeded:
            raise SystemExit(1)

        logger.debug(
            "diff: file1=%d rows, file2=%d rows, added=%d, removed=%d, changed=%d",
            count1,
            count2,
            len(added),
            len(removed),
            len(changed),
        )
