"""Sniff command module - detect file properties."""

import csv
import itertools
import logging
from typing import Any

from ..common.command_utils import get_iterable_options
from ..utils import get_option

logger = logging.getLogger(__name__)

# Records read to describe the fields.
SAMPLE_ROWS = 100


class Sniffer:
    """Sniffer command handler - detect file properties."""

    def __init__(self):
        pass

    def sniff(self, fromfile, options=None):
        """Detect file properties: format, compression, encoding, delimiter, fields, count.

        Args:
            fromfile: Input path.
            options: Command options (reader options, ``format_out``, ``output``).
        """
        if options is None:
            options = {}
        logger.debug("Sniffing %s", fromfile)
        result = sniff_file(fromfile, options)

        format_type = (
            get_option(options, "format_out") or get_option(options, "format") or ""
        ).lower()
        to_file = get_option(options, "output")
        if not format_type:
            if to_file and str(to_file).lower().endswith(".json"):
                format_type = "json"
            elif to_file and str(to_file).lower().endswith((".yaml", ".yml")):
                format_type = "yaml"
            else:
                format_type = "text"

        if format_type == "json":
            from ..common.results import SNIFF, emit

            emit(SNIFF, result, output=to_file)
            return
        if format_type == "yaml":
            import yaml

            output_text = yaml.safe_dump(result, sort_keys=False, allow_unicode=True).rstrip()
        else:
            output_text = _text_report(result)
        if to_file:
            with open(to_file, "w", encoding="utf8") as out:
                out.write(output_text)
                out.write("\n")
        else:
            print(output_text)


def sniff_file(fromfile: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Properties of a file (the payload of the ``undatum.sniff/1`` result).

    Args:
        fromfile: Input path.
        options: Reader options (``format_in``, ``delimiter``, ``encoding``, ...).

    Returns:
        ``file``, ``filetype``, ``compression``, ``encoding``, ``delimiter``,
        ``has_header``, ``record_count``, ``sample_size`` and ``fields``.
    """
    from ..common.command_utils import resolve_csv_delimiter
    from ..constants import TEXT_DATA_TYPES
    from ..io import RowSource
    from .counter import count_records

    options = options or {}
    source = RowSource(fromfile, options)
    filetype, compression = source._detected()
    filetype = source.format_id or filetype or "unknown"
    iterableargs = get_iterable_options(options)

    encoding = iterableargs.get("encoding")
    if not encoding and filetype in TEXT_DATA_TYPES and compression is None:
        from ..utils import detect_encoding

        try:
            encoding = (detect_encoding(fromfile) or {}).get("encoding")
        except Exception:  # noqa: BLE001 - detection is best effort
            encoding = None

    delimiter = None
    has_header = None
    if filetype in ("csv", "tsv"):
        delimiter = resolve_csv_delimiter(iterableargs, filename=fromfile, filetype=filetype)
        if compression is None:
            has_header = _has_header(fromfile, encoding or "utf8", delimiter)

    fields: dict[str, dict[str, Any]] = {}
    sample_size = 0
    for item in itertools.islice(source, SAMPLE_ROWS):
        if not isinstance(item, dict):
            continue
        sample_size += 1
        for name, value in item.items():
            info = fields.setdefault(name, {"type": "string", "examples": []})
            if value is None:
                continue
            if isinstance(value, bool):
                info["type"] = "boolean"
            elif isinstance(value, int):
                if info["type"] == "string":
                    info["type"] = "integer"
            elif isinstance(value, float):
                info["type"] = "number"
            elif isinstance(value, (list, dict)):
                info["type"] = "object"
            if len(info["examples"]) < 3:
                info["examples"].append(str(value)[:50])

    return {
        "file": fromfile,
        "filetype": filetype,
        "compression": compression,
        "encoding": encoding,
        "delimiter": delimiter,
        "has_header": has_header,
        "record_count": count_records(fromfile, options),
        "sample_size": sample_size,
        "fields": fields,
    }


def _has_header(path: str, encoding: str, delimiter: str | None) -> bool | None:
    """``csv.Sniffer`` header guess on the first 64 KB, ``None`` when it cannot tell."""
    try:
        with open(path, encoding=encoding, errors="replace", newline="") as handle:
            sample = handle.read(65536)
        if not sample.strip():
            return None
        return csv.Sniffer().has_header(sample)
    except (csv.Error, OSError, LookupError):
        return None


def _text_report(result: dict[str, Any]) -> str:
    lines = [
        f"File: {result['file']}",
        f"Type: {result['filetype']}",
    ]
    if result["compression"]:
        lines.append(f"Compression: {result['compression']}")
    if result["encoding"]:
        lines.append(f"Encoding: {result['encoding']}")
    if result["delimiter"]:
        lines.append(f"Delimiter: {result['delimiter']!r}")
    if result["has_header"] is not None:
        lines.append(f"Header: {'yes' if result['has_header'] else 'no'}")
    lines.append(f"Records: {result['record_count']}")
    lines.append(f"\nFields ({len(result['fields'])}):")
    for name, info in result["fields"].items():
        lines.append(f"  {name}: {info['type']}")
        if info["examples"]:
            lines.append(f"    Examples: {', '.join(info['examples'][:3])}")
    return "\n".join(lines)
