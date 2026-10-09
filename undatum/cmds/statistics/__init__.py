"""Statistical analysis package.

Split from the former monolithic ``undatum/cmds/statistics.py`` into
engine detection, DuckDB engine, and iterable engine modules.
"""

import logging

import duckdb
from qddate import DateParser

from ...common.command_utils import (  # noqa: F401
    ITERABLE_OPTIONS_KEYS,
    force_iterable_if_table,
    get_iterable_options,
)
from ...utils import TypeGuesser, get_option
from .duckdb_engine import DuckDBStatsMixin
from .engine import _detect_engine
from .iterable_engine import IterableStatsMixin

logger = logging.getLogger(__name__)

__all__ = ["StatProcessor", "_detect_engine"]


class StatProcessor(DuckDBStatsMixin, IterableStatsMixin):
    """Statistical processing handler."""

    def __init__(self, nodates=True):
        if nodates:
            self.qd = None
        else:
            self.qd = DateParser(generate=True)
        self.types = TypeGuesser(self.qd)

    def stats(self, fromfile, options):
        """Produces statistics and structure analysis of JSONlines, BSON or CSV file and produces stats.

        Args:
            fromfile: Path to input file
            options: Dictionary of options including:
                - engine: Engine to use ('auto', 'duckdb', or 'iterable')
                - dictshare: Dictionary share threshold
                - format_in: Override file type detection
                - progress: Show progress bar (default: True)
                - no_progress: Disable progress bar
                - Other iterable options (delimiter, encoding, etc.)
        """
        self.types = TypeGuesser(self.qd)  # per file: date probes are per field name
        # Get engine preference and detect appropriate engine
        engine = get_option(options, "engine") or "auto"
        filetype = get_option(options, "format_in")
        flatten_nested = bool(get_option(options, "flatten_nested"))
        if flatten_nested:
            detected_engine = "iterable"
        else:
            detected_engine = _detect_engine(fromfile, engine, filetype)
        detected_engine = force_iterable_if_table(options, detected_engine)

        output = get_option(options, "output")
        format_out = _resolve_stats_format(
            get_option(options, "format_out") or get_option(options, "output_format"),
            output,
        )
        if format_out in {"json", "html", "markdown"}:
            options = dict(options)
            options["quiet"] = True
            options["progress"] = False
            options["no_progress"] = True

        logger.info(f"Using {detected_engine} engine for statistics computation")

        # Validate input file before processing
        from ...common.errors import FileNotFoundError, PermissionError, find_similar_files
        from ...common.path_utils import validate_file_path

        try:
            validate_file_path(fromfile, check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(fromfile)
            raise FileNotFoundError(fromfile, suggestions) from e
        except PermissionError as e:
            raise PermissionError(fromfile, operation="read") from e

        profile = None
        # Use DuckDB engine if selected
        if detected_engine == "duckdb":
            try:
                profile = self._stats_duckdb(fromfile, options)
            except duckdb.Error as e:
                # Check if this is a None column reference error (which is handled gracefully)
                error_msg = str(e)
                if "None" in error_msg and (
                    "not found" in error_msg or "Referenced column" in error_msg
                ):
                    # None column reference - this is expected and handled, suppress warning
                    logger.debug(
                        f"DuckDB stats: None column reference detected, falling back to iterable: {e}"
                    )
                else:
                    # DuckDB-specific errors (query failures, parsing errors, etc.)
                    logger.warning(
                        f"DuckDB stats failed (DuckDB error), falling back to iterable: {e}"
                    )
                detected_engine = "iterable"
            except Exception as e:
                # Check if this is a None column reference error
                error_msg = str(e)
                if "None" in error_msg and (
                    "not found" in error_msg or "Referenced column" in error_msg
                ):
                    # None column reference - suppress warning
                    logger.debug(
                        f"DuckDB stats: None column reference detected, falling back to iterable: {e}"
                    )
                else:
                    # Other errors (file not found, permission errors, etc.)
                    logger.warning(f"DuckDB stats failed, falling back to iterable: {e}")
                detected_engine = "iterable"

        # Use iterable engine (existing implementation)
        if profile is None and detected_engine == "iterable":
            profile = self._stats_iterable(fromfile, options)
        elif profile is None:
            from ...common.errors import ValidationError

            raise ValidationError(
                f"Unsupported engine: '{detected_engine}'",
                field="engine",
                suggestions=["auto", "duckdb", "python"],
            )

        if format_out == "json":
            _emit_stats_json(profile, output)
        elif format_out in {"html", "markdown"}:
            _emit_stats_report(profile, format_out, output)
        return profile


_STATS_EXT_FORMATS = {
    ".json": "json",
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
}


def _resolve_stats_format(format_out: str | None, output: str | None) -> str:
    """Resolve stats output format from ``--format-out`` or the output path."""
    if format_out:
        value = str(format_out).lower().strip()
        if value == "md":
            return "markdown"
        return value
    if output:
        lower = str(output).lower()
        for suffix, fmt in _STATS_EXT_FORMATS.items():
            if lower.endswith(suffix):
                return fmt
    return ""


def _profile_table_rows(profile: dict) -> list[tuple[str, ...]]:
    """Build display rows from a stats profile."""
    debug = profile.get("debug") or {}
    fielddata = debug.get("fielddata") or {}
    finfields = profile.get("fieldtypes") or {}
    rows = []
    for fd in fielddata.values():
        type_category = fd.get("type_category", "mixed")
        missing_rate = fd.get("missing_rate", 0.0)
        missing_count = fd.get("missing_count", 0)
        cardinality_pct = fd.get("cardinality_pct", fd.get("share_uniq", 0.0))
        if fd.get("is_numerical"):
            mean = fd.get("mean")
            median = fd.get("median")
            if mean is not None and median is not None:
                distribution = f"μ={mean:.2f}, m={median:.2f}"
            else:
                distribution = "-"
        else:
            distribution = "-"
        avglen = fd.get("avglen", 0.0)
        rows.append(
            (
                str(fd.get("key", "")),
                str(finfields.get(fd.get("key"), "str")),
                str(type_category),
                f"{missing_count} ({missing_rate}%)",
                f"{fd.get('n_uniq', 0)} ({cardinality_pct}%)",
                distribution,
                str(fd.get("minlen", "-")),
                str(fd.get("maxlen", "-")),
                f"{avglen:.1f}" if isinstance(avglen, (int, float)) else str(avglen),
            )
        )
    return rows


def _emit_stats_json(profile: dict, output: str | None) -> None:
    """Write a stats profile as JSON to a file or stdout."""
    from ...common.results import STATS, dumps, envelope

    _write_stats_text(dumps(envelope(STATS, profile)), output)


def _emit_stats_report(profile: dict, format_out: str, output: str | None) -> None:
    """Write an HTML or Markdown profiling report."""
    headers = (
        "Field",
        "Type",
        "Category",
        "Missing",
        "Cardinality",
        "Distribution",
        "MinLen",
        "MaxLen",
        "AvgLen",
    )
    rows = _profile_table_rows(profile)
    count = profile.get("count", "")
    num_fields = profile.get("num_fields", len(rows))
    if format_out == "html":
        payload = _stats_html(headers, rows, count, num_fields)
    else:
        payload = _stats_markdown(headers, rows, count, num_fields)
    _write_stats_text(payload, output)


def _write_stats_text(payload: str, output: str | None) -> None:
    if output:
        with open(output, "w", encoding="utf8") as handle:
            handle.write(payload)
            if not payload.endswith("\n"):
                handle.write("\n")
    else:
        print(payload)


def _html_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _stats_html(headers, rows, count, num_fields) -> str:
    head = "".join(f"<th>{_html_escape(h)}</th>" for h in headers)
    body = []
    for row in rows:
        cells = "".join(f"<td>{_html_escape(cell)}</td>" for cell in row)
        body.append(f"<tr>{cells}</tr>")
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        "<title>Dataset Profile</title>"
        "<style>body{font-family:sans-serif;margin:1.5rem}"
        "table{border-collapse:collapse}th,td{border:1px solid #ccc;padding:.4rem .6rem}"
        "th{background:#f4f4f4;text-align:left}</style></head><body>"
        "<h1>Dataset Profile</h1>"
        f"<p>Rows: {_html_escape(count)} &middot; Fields: {_html_escape(num_fields)}</p>"
        f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table>"
        "</body></html>\n"
    )


def _stats_markdown(headers, rows, count, num_fields) -> str:
    lines = [
        "# Dataset Profile",
        "",
        f"Rows: {count} · Fields: {num_fields}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |")
    lines.append("")
    return "\n".join(lines)
