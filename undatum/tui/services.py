"""TUI data adapters. This module must not import Textual."""

from __future__ import annotations

import re
from typing import Any

from ..common.command_utils import get_iterable_options, iter_command_rows
from ..common.errors import ValidationError
from ..common.path_utils import is_uri, validate_file_path
from ..common.s3_iterable import open_path
from ..utils import get_file_type, get_option
from .actions import DEFAULT_SQL_LIMIT
from .session import DEFAULT_SAMPLE_LIMIT, MAX_SAMPLE_LIMIT, SessionState


def clamp_sample_limit(limit: int | None) -> int:
    """Return a sample size within the UI memory budget.

    Args:
        limit: Requested row count. ``None`` uses the default.

    Returns:
        Limit between 1 and ``MAX_SAMPLE_LIMIT``.

    Raises:
        ValidationError: If ``limit`` is less than 1.
    """
    if limit is None:
        return DEFAULT_SAMPLE_LIMIT
    if limit < 1:
        raise ValidationError("Sample limit must be at least 1", field="limit")
    return min(int(limit), MAX_SAMPLE_LIMIT)


def _headers_from_rows(rows: list[dict[str, Any]]) -> list[str]:
    headers: list[str] = []
    seen = set()
    for row in rows:
        for key in row:
            if key not in seen:
                seen.add(key)
                headers.append(str(key))
    return headers


def _infer_field_types(rows: list[dict[str, Any]], headers: list[str]) -> dict[str, str]:
    types: dict[str, str] = {}
    for header in headers:
        found = set()
        for row in rows:
            value = row.get(header)
            if value is None or value == "":
                continue
            if isinstance(value, bool):
                found.add("bool")
            elif isinstance(value, int):
                found.add("int")
            elif isinstance(value, float):
                found.add("float")
            else:
                found.add("str")
        if not found:
            types[header] = "empty"
        elif len(found) == 1:
            types[header] = found.pop()
        else:
            types[header] = "mixed"
    return types


def _cell_text(value: Any, max_len: int = 80) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


_SQL_LIMIT_RE = re.compile(r"\blimit\s+\d+\b", re.IGNORECASE)


def ensure_sql_limit(query: str, default_limit: int = DEFAULT_SQL_LIMIT) -> tuple[str, bool]:
    """Return a query that has a LIMIT, injecting one when the user omitted it.

    Args:
        query: SQL text.
        default_limit: LIMIT to wrap with when none is present.

    Returns:
        ``(query, injected)`` where ``injected`` is True if a LIMIT was added.
    """
    stripped = (query or "").strip().rstrip(";").strip()
    if not stripped:
        return stripped, False
    if _SQL_LIMIT_RE.search(stripped):
        return stripped, False
    wrapped = f"SELECT * FROM (\n{stripped}\n) AS _undatum_tui LIMIT {int(default_limit)}"
    return wrapped, True


class TuiServices:
    """Synchronous helpers used by TUI screens."""

    def load_sample(
        self,
        path: str,
        options: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> SessionState:
        """Open a dataset and read a bounded sample of rows.

        Args:
            path: Local file path or cloud URI.
            options: CLI-style options (encoding, delimiter, format_in, ...).
            limit: Sample size before clamping.

        Returns:
            SessionState with sample rows and headers.

        Raises:
            FileNotFoundError: If a local path does not exist.
            ValidationError: If ``limit`` is invalid.
        """
        options = dict(options or {})
        sample_limit = clamp_sample_limit(limit)
        if not is_uri(path):
            validate_file_path(path, check_read=True)

        iterableargs = get_iterable_options(options)
        format_in = get_option(options, "format_in") or get_option(options, "filetype")
        encoding = get_option(options, "encoding")
        rows: list[dict[str, Any]] = []
        truncated = False
        iterable = open_path(path, mode="r", iterableargs=iterableargs)
        try:
            for item in iter_command_rows(iterable, options):
                if not isinstance(item, dict):
                    continue
                if len(rows) == sample_limit:
                    truncated = True
                    break
                rows.append(item)
        finally:
            iterable.close()

        headers = _headers_from_rows(rows)
        format_name = format_in or get_file_type(path) or "unknown"
        return SessionState(
            source=path,
            options=options,
            sample_rows=rows,
            sample_limit=sample_limit,
            headers=headers,
            field_types=_infer_field_types(rows, headers),
            last_cli=f"undatum table {path} --limit {sample_limit}",
            format_name=format_name,
            encoding=encoding or iterableargs.get("encoding"),
            truncated=truncated,
        )

    def grid_rows(self, session: SessionState) -> list[list[str]]:
        """Stringify visible (filtered) sample rows in header order for a DataTable."""
        return [
            [_cell_text(row.get(header)) for header in session.headers]
            for row in session.visible_rows()
        ]

    def apply_filter(self, session: SessionState, expr: str | None) -> SessionState:
        """Filter the in-memory sample. Empty expression clears the filter."""
        from ..common.filter import match_filter

        cleaned = (expr or "").strip() or None
        if cleaned:
            probe = session.sample_rows[0] if session.sample_rows else {}
            try:
                match_filter(probe, cleaned)
            except Exception as exc:
                raise ValidationError(f"Invalid filter: {exc}", field="filter") from exc
            session.filter_expr = cleaned
            session.last_cli = f'undatum select {session.source} --filter "{cleaned}"'
        else:
            session.filter_expr = None
            session.last_cli = f"undatum table {session.source} --limit {session.sample_limit}"
        return session

    def profile(self, session: SessionState) -> tuple[list[str], list[list[str]], str]:
        """Run ``StatProcessor`` on the source file with progress disabled."""
        from ..cmds.statistics import StatProcessor, _profile_table_rows

        options = dict(session.options)
        options.update({"quiet": True, "progress": False, "no_progress": True})
        profile = StatProcessor().stats(session.source, options) or {}
        headers = ["Field", "Type", "Category", "Missing", "Cardinality", "Distribution"]
        rows = [list(row[:6]) for row in _profile_table_rows(profile)]
        count = profile.get("count", "")
        cli = f"undatum stats {session.source}"
        session.last_cli = cli
        return headers, rows, f"{cli}  (rows={count})"

    def frequency(
        self, session: SessionState, field: str
    ) -> tuple[list[str], list[list[str]], str]:
        """Value counts for one field on the current (filtered) sample."""
        from ..cmds.selector import get_iterable_fields_freq

        if field not in session.headers:
            raise ValidationError(f"Unknown field: {field}", field="fields")
        items = get_iterable_fields_freq(
            session.visible_rows(), [field], dolog=False, filter_expr=None
        )
        headers = [field, "count"]
        rows = [[str(item[0]), str(item[-1])] for item in items]
        cli = f"undatum frequency {session.source} --fields {field}"
        if session.filter_expr:
            cli += f' --filter "{session.filter_expr}"'
        if session.truncated:
            cli += "  # counts are for the loaded sample"
        session.last_cli = cli
        return headers, rows, cli

    def export_view(self, session: SessionState, path: str) -> str:
        """Write the current visible sample through Dataset.write / convert."""
        from ..sdk.dataset import Dataset

        if not path or not str(path).strip():
            raise ValidationError("Export path is required", field="output")
        rows = session.visible_rows()
        # Temp JSONL is the convert source; do not pass the original format_in.
        Dataset(data=iter(rows), options={}).write(path, progress=False)
        if session.filter_expr:
            cli = (
                f'undatum select {session.source} --filter "{session.filter_expr}" --output {path}'
            )
        else:
            cli = f"undatum convert {session.source} {path}"
        session.last_cli = cli
        return cli

    def run_sql(self, session: SessionState, query: str) -> tuple[list[str], list[list[str]], str]:
        """Run DuckDB SQL against the source file via ``SqlExecutor.fetch``."""
        from ..cmds.sql import SqlExecutor

        cleaned = (query or "").strip()
        if not cleaned:
            raise ValidationError("SQL query is required", field="query")
        final_query, injected = ensure_sql_limit(cleaned, DEFAULT_SQL_LIMIT)
        columns, records, truncated = SqlExecutor().fetch(
            final_query,
            [session.source],
            dict(session.options),
            max_rows=MAX_SAMPLE_LIMIT,
        )
        headers = [str(col) for col in columns]
        rows = [[_cell_text(record.get(header)) for header in headers] for record in records]
        one_line = " ".join(final_query.split())
        cli = f'undatum sql "{one_line}" {session.source}'
        if injected:
            cli += f"  # LIMIT {DEFAULT_SQL_LIMIT} added"
        if truncated:
            cli += f"  # showing first {MAX_SAMPLE_LIMIT} rows"
        session.last_cli = cli
        return headers, rows, cli

    def convert_save(self, session: SessionState, path: str) -> str:
        """Convert the source file (not just the sample) with ``--low-memory``."""
        from ..cmds.converter import Converter

        dest = (path or "").strip()
        if not dest:
            raise ValidationError("Output path is required", field="output")
        if dest == session.source:
            raise ValidationError("Output path must differ from the source file", field="output")
        options = dict(session.options)
        options.update({"progress": False, "no_progress": True, "low_memory": True})
        Converter().convert(session.source, dest, options)
        cli = f"undatum convert {session.source} {dest} --low-memory"
        session.last_cli = cli
        return cli

    def validate_sample(
        self, session: SessionState, rules_file: str | None = None
    ) -> tuple[list[str], list[list[str]], str]:
        """Validate the loaded sample. Full-file validate remains a CLI job."""
        from ..common.validation_rules import ValidationRule, ValidationRuleError, ValidationRuleSet

        rows = session.visible_rows()
        cleaned_rules = (rules_file or "").strip() or None
        if cleaned_rules:
            from ..common.validation_rules import parse_validation_rules

            try:
                rule_set = parse_validation_rules(cleaned_rules)
            except ValidationRuleError as exc:
                raise ValidationError(str(exc), field="rules") from exc
            violations: list[list[str]] = []
            for index, record in enumerate(rows):
                for item in rule_set.validate_record(record, index):
                    violations.append(
                        [
                            str(item.get("row", index)),
                            str(item.get("field") or ""),
                            str(item.get("severity") or ""),
                            str(item.get("message") or ""),
                        ]
                    )
            cli = (
                f"undatum validate {session.source} --rules {cleaned_rules}  "
                "# sample only; full-file validate is CLI"
            )
            session.last_cli = cli
            if violations:
                return ["Row", "Field", "Severity", "Message"], violations, cli
            return (
                ["Row", "Field", "Severity", "Message"],
                [["-", "-", "ok", f"No violations in {len(rows)} sample rows"]],
                cli,
            )

        rule_set = ValidationRuleSet(
            [
                ValidationRule(
                    {
                        "field": header,
                        "type": "field",
                        "required": True,
                        "name": f"{header} present",
                    }
                )
                for header in session.headers
            ]
        )
        headers = ["Field", "Missing", "Empty", "Sample rows"]
        table: list[list[str]] = []
        for header in session.headers:
            missing = sum(1 for record in rows if record.get(header) is None)
            empty = sum(
                1 for record in rows if record.get(header) is None or record.get(header) == ""
            )
            table.append([header, str(missing), str(empty), str(len(rows))])
        extra = 0
        for index, record in enumerate(rows):
            extra += len(rule_set.validate_record(record, index))
        cli = (
            f"undatum validate {session.source}  "
            f"# sample completeness ({extra} required-field issues); full-file needs --rules"
        )
        session.last_cli = cli
        return headers, table, cli

    def mask_preview(
        self, session: SessionState, fields: str, method: str = "redact"
    ) -> tuple[list[str], list[list[str]], str]:
        """Mask selected fields on the visible sample (preview only)."""
        from ..common.masking import mask_value

        field_list = [item.strip() for item in (fields or "").split(",") if item.strip()]
        if not field_list:
            raise ValidationError("Specify at least one field to mask", field="fields")
        unknown = [item for item in field_list if item not in session.headers]
        if unknown:
            raise ValidationError(f"Unknown field: {unknown[0]}", field="fields")
        method_name = (method or "redact").strip() or "redact"
        preview_rows = []
        for record in session.visible_rows():
            masked = dict(record)
            for field_name in field_list:
                masked[field_name] = mask_value(record.get(field_name), method_name, field_name)
            preview_rows.append([_cell_text(masked.get(header)) for header in session.headers])
        cli = (
            f"undatum mask {session.source} --fields {','.join(field_list)} "
            f"--method {method_name}  # preview of sample; write via mask save"
        )
        session.last_cli = cli
        return list(session.headers), preview_rows, cli

    def mask_write(
        self, session: SessionState, path: str, fields: str, method: str = "redact"
    ) -> str:
        """Mask the source file through ``Masker`` (full file)."""
        from ..cmds.masker import Masker

        dest = (path or "").strip()
        if not dest:
            raise ValidationError("Output path is required", field="output")
        field_list = [item.strip() for item in (fields or "").split(",") if item.strip()]
        if not field_list:
            raise ValidationError("Specify at least one field to mask", field="fields")
        method_name = (method or "redact").strip() or "redact"
        options = dict(session.options)
        options.update(
            {
                "fields": ",".join(field_list),
                "method": method_name,
                "progress": False,
                "no_progress": True,
            }
        )
        Masker().mask(session.source, dest, options)
        cli = (
            f"undatum mask {session.source} --output {dest} --fields {','.join(field_list)} "
            f"--method {method_name}"
        )
        session.last_cli = cli
        return cli

    def build_pipeline_spec(self, session: SessionState) -> dict[str, Any]:
        """Build a pipeline YAML structure from the current session."""
        steps: list[dict[str, Any]] = [
            {
                "name": "convert",
                "command": "convert",
                "args": {"input": session.source, "output": "out.jsonl"},
            }
        ]
        if session.filter_expr:
            steps.append(
                {
                    "name": "select",
                    "command": "select",
                    "args": {
                        "input": "$convert",
                        "output": "filtered.jsonl",
                        "filter": session.filter_expr,
                    },
                }
            )
        return {"steps": steps}

    def export_pipeline(self, session: SessionState, path: str) -> str:
        """Write a pipeline YAML snippet for the current session."""
        import yaml

        dest = (path or "").strip()
        if not dest:
            raise ValidationError("Pipeline path is required", field="output")
        spec = self.build_pipeline_spec(session)
        text = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True)
        with open(dest, "w", encoding="utf-8") as handle:
            handle.write(text)
        cli = f"undatum pipeline run {dest}"
        session.last_cli = cli
        return cli
