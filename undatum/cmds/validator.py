"""Data validation module."""

import csv
import difflib
import json
import logging
import sys
from collections import defaultdict
from typing import Any

import orjson

from ..common.chunked_io import chunked_reader
from ..common.command_utils import get_iterable_options, iter_command_rows
from ..common.errors import (
    FileNotFoundError,
    FormatError,
    PermissionError,
    ValidationError,
    find_similar_files,
)
from ..common.filter import match_filter
from ..common.parallel import parallel_process_chunks
from ..common.parallel_workers import validate_rules_chunk
from ..common.path_utils import validate_file_path
from ..common.progress import wrap_iterable
from ..common.validation_rules import parse_validation_rules
from ..utils import field_values, get_file_type, get_option, normalize_for_json
from ..validate import VALIDATION_RULEMAP

logger = logging.getLogger(__name__)

# Output modes of the legacy --fields/--rule validation.
LEGACY_MODES = {"stats", "invalid", "valid", "all"}


class Validator:
    """Data validation handler."""

    def __init__(self):
        pass

    def validate(self, fromfile, options=None):
        """Validates data against validation rules.

        Supports two modes:
        1. Rule file mode: Use --rules option with YAML/JSON rule file
        2. Legacy CLI mode: Use --fields and --rule options (backward compatible)
        """
        if options is None:
            options = {}

        # Validate input file exists and is readable
        try:
            validate_file_path(fromfile, check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(fromfile)
            raise FileNotFoundError(fromfile, suggestions) from e
        except PermissionError as e:
            raise PermissionError(fromfile, operation="read") from e

        logger.debug("Processing %s", fromfile)

        # Check if using rule file mode
        rules_file = get_option(options, "rules")
        if rules_file:
            self._validate_with_rules(fromfile, options, rules_file)
        else:
            self._validate_legacy(fromfile, options)

    def _validate_with_rules(self, fromfile, options, rules_file):
        """Validate using rule file."""
        rule_set = parse_validation_rules(rules_file)

        # Process records and collect violations
        all_violations = []
        total_records = 0

        from ..common.s3_iterable import open_path as open_iterable

        iterableargs = get_iterable_options(options)
        it_in = open_iterable(fromfile, mode="r", iterableargs=iterableargs)

        show_progress = get_option(options, "progress") or False
        filter_expr = options.get("filter")
        threads = get_option(options, "threads")
        use_parallel = bool(threads) and int(threads) > 1
        if use_parallel and rule_set.stateful:
            # 'unique' remembers values across records: one process sees them all.
            logger.info("validate: unique rules run in one process; ignoring --threads")
            use_parallel = False

        try:
            records = wrap_iterable(
                iter_command_rows(it_in, options),
                desc="Validating",
                unit="rows",
                show_progress=show_progress,
            )
            if use_parallel:
                chunk_size = int(options.get("batch_size") or 1000)
                start_index = 0

                def _payloads():
                    nonlocal start_index
                    for chunk in chunked_reader(records, chunk_size=chunk_size):
                        payload = (list(chunk), start_index, rules_file, filter_expr)
                        start_index += len(payload[0])
                        yield payload

                for violations, seen in parallel_process_chunks(
                    validate_rules_chunk,
                    _payloads(),
                    num_threads=int(threads),
                    use_processes=True,
                    preserve_order=False,
                ):
                    total_records += seen
                    all_violations.extend(violations)
                all_violations.sort(key=lambda v: v.get("row", 0))
            else:
                for record_index, record in enumerate(records):
                    total_records += 1
                    if filter_expr and not match_filter(record, filter_expr):
                        continue
                    violations = rule_set.validate_record(record, record_index)
                    all_violations.extend(violations)
        finally:
            rule_set.close()
            if hasattr(it_in, "close"):
                it_in.close()

        # Generate reports
        self._generate_validation_report(all_violations, total_records, options)

    def _validate_legacy(self, fromfile, options):
        """Legacy validation mode: apply one built-in rule to one field."""
        fields_value = get_option(options, "fields")
        if not fields_value:
            raise ValidationError(
                "validate requires --rules, or --fields with --rule", field="fields"
            )
        field = fields_value.split(",")[0]
        rule = get_option(options, "rule")
        if not rule:
            raise ValidationError("validate requires --rule with --fields", field="rule")
        if rule not in VALIDATION_RULEMAP:
            close = difflib.get_close_matches(rule, list(VALIDATION_RULEMAP), n=3)
            raise ValidationError(
                f"Unknown rule '{rule}'",
                field="rule",
                suggestions=close or sorted(VALIDATION_RULEMAP),
            )
        val_func = VALIDATION_RULEMAP[rule]
        mode = options.get("mode") or "stats"
        if mode not in LEGACY_MODES:
            raise ValidationError(
                f"Invalid mode '{mode}'", field="mode", suggestions=sorted(LEGACY_MODES)
            )
        to_file = get_option(options, "output")
        if to_file and not get_file_type(to_file):
            raise FormatError(to_file, to_file.rsplit(".", 1)[-1])

        from ..common.s3_iterable import open_path as open_iterable

        iterableargs = get_iterable_options(options)
        filter_expr = options.get("filter")
        validated = []
        stats = {"total": 0, "invalid": 0, "novalue": 0}
        iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
        try:
            for record in iter_command_rows(iterable, options):
                if filter_expr is not None and not match_filter(record, filter_expr):
                    continue
                stats["total"] += 1
                values = field_values(record, field)
                if not values:
                    stats["novalue"] += 1
                    continue
                valid = bool(val_func(values[0]))
                if not valid:
                    stats["invalid"] += 1
                validated.append({field: values[0], field + "_valid": valid})
        finally:
            iterable.close()

        stats["share"] = 100.0 * stats["invalid"] / stats["total"] if stats["total"] > 0 else 0
        logger.debug(
            "validate: %d of %d records not valid and %d without a value against %s",
            stats["invalid"],
            stats["total"],
            stats["novalue"],
            rule,
        )

        if (get_option(options, "output_format") or "").lower() == "json":
            from ..common.results import VALIDATE_RULE, emit

            document: dict[str, Any] = {
                "rule": rule,
                "field": field,
                "mode": mode,
                "statistics": stats,
            }
            if mode != "stats":
                document["records"] = [
                    row
                    for row in validated
                    if mode == "all" or (mode == "invalid") != row[field + "_valid"]
                ]
            emit(VALIDATE_RULE, document, output=to_file)
            return

        out = open(to_file, "w", encoding="utf8", newline="") if to_file else sys.stdout
        try:
            if mode == "stats":
                out.write(orjson.dumps(stats, option=orjson.OPT_INDENT_2).decode("utf8"))
                out.write("\n")
                return
            writer = csv.DictWriter(
                out,
                fieldnames=[field, field + "_valid"],
                delimiter=get_option(options, "delimiter") or ",",
            )
            for row in validated:
                is_valid = row[field + "_valid"]
                if mode == "all" or (mode == "invalid") != is_valid:
                    writer.writerow(row)
        finally:
            if to_file:
                out.close()

    def _generate_validation_report(self, violations, total_records, options):
        """Generate validation report from violations.

        Args:
            violations: List of violation dictionaries
            total_records: Total number of records processed
            options: Validation options
        """
        output_format = get_option(options, "output_format") or "text"
        severity_filter = get_option(options, "severity") or "all"
        violation_report_file = get_option(options, "violation_report")

        # Filter violations by severity
        if severity_filter != "all":
            violations = [v for v in violations if v["severity"] == severity_filter]

        # Calculate statistics
        stats = {
            "total_records": total_records,
            "total_violations": len(violations),
            "errors": len([v for v in violations if v["severity"] == "error"]),
            "warnings": len([v for v in violations if v["severity"] == "warning"]),
            "info": len([v for v in violations if v["severity"] == "info"]),
            "passed": total_records - len({v["row"] for v in violations}),
        }

        # Group violations by field and rule
        violations_by_field = defaultdict(list)
        violations_by_rule = defaultdict(list)
        for v in violations:
            if v["field"]:
                violations_by_field[v["field"]].append(v)
            violations_by_rule[v["rule"]].append(v)

        # Generate report
        if output_format == "jsonl":
            self._generate_jsonl_report(violations, stats, options)
        elif output_format == "json":
            self._generate_json_report(
                violations, stats, violations_by_field, violations_by_rule, options
            )
        else:
            self._generate_text_report(
                violations, stats, violations_by_field, violations_by_rule, options
            )

        # Write detailed violation report if requested
        if violation_report_file:
            with open(violation_report_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "statistics": stats,
                        "violations": violations,
                        "violations_by_field": {k: len(v) for k, v in violations_by_field.items()},
                        "violations_by_rule": {k: len(v) for k, v in violations_by_rule.items()},
                    },
                    f,
                    indent=2,
                    default=str,
                )

    def _generate_text_report(
        self, violations, stats, violations_by_field, violations_by_rule, options
    ):
        """Generate text format validation report."""
        from rich.console import Console
        from rich.table import Table

        console = Console()

        # Summary table
        summary_table = Table(
            title="Validation Summary", show_header=True, header_style="bold magenta"
        )
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green", justify="right")
        summary_table.add_column("Percentage", style="yellow", justify="right")

        summary_table.add_row("Total Records", str(stats["total_records"]), "100.0%")
        summary_table.add_row(
            "Errors",
            str(stats["errors"]),
            (
                f"{stats['errors'] / stats['total_records'] * 100:.2f}%"
                if stats["total_records"] > 0
                else "0.0%"
            ),
        )
        summary_table.add_row(
            "Warnings",
            str(stats["warnings"]),
            (
                f"{stats['warnings'] / stats['total_records'] * 100:.2f}%"
                if stats["total_records"] > 0
                else "0.0%"
            ),
        )
        summary_table.add_row(
            "Info",
            str(stats["info"]),
            (
                f"{stats['info'] / stats['total_records'] * 100:.2f}%"
                if stats["total_records"] > 0
                else "0.0%"
            ),
        )
        summary_table.add_row(
            "Passed",
            str(stats["passed"]),
            (
                f"{stats['passed'] / stats['total_records'] * 100:.2f}%"
                if stats["total_records"] > 0
                else "0.0%"
            ),
        )

        console.print(summary_table)
        console.print()

        # Violations by field
        if violations_by_field:
            field_table = Table(
                title="Violations by Field", show_header=True, header_style="bold magenta"
            )
            field_table.add_column("Field", style="cyan")
            field_table.add_column("Total", style="green", justify="right")
            field_table.add_column("Errors", style="red", justify="right")
            field_table.add_column("Warnings", style="yellow", justify="right")

            for field, field_violations in sorted(
                violations_by_field.items(), key=lambda x: len(x[1]), reverse=True
            ):
                errors = len([v for v in field_violations if v["severity"] == "error"])
                warnings = len([v for v in field_violations if v["severity"] == "warning"])
                field_table.add_row(field, str(len(field_violations)), str(errors), str(warnings))

            console.print(field_table)
            console.print()

        # Show sample violations
        if violations:
            max_violations = options.get("max_violations", 10)
            sample_violations = violations[:max_violations]

            violations_table = Table(
                title=f"Sample Violations (showing {len(sample_violations)} of {len(violations)})",
                show_header=True,
                header_style="bold magenta",
            )
            violations_table.add_column("Record", style="cyan", justify="right")
            violations_table.add_column("Field", style="yellow")
            violations_table.add_column("Severity", style="red")
            violations_table.add_column("Message", style="white")

            for v in sample_violations:
                severity_style = {"error": "red", "warning": "yellow", "info": "blue"}.get(
                    v["severity"], "white"
                )
                violations_table.add_row(
                    str(v["row"]),
                    v["field"] or "cross-field",
                    f"[{severity_style}]{v['severity']}[/{severity_style}]",
                    v["message"],
                )

            console.print(violations_table)

            if len(violations) > max_violations:
                console.print(
                    f"\n[dim]... and {len(violations) - max_violations} more violations. Use --violation-report to see all.[/dim]"
                )

        # Exit code based on failures
        fail_on_warnings = options.get("fail_on_warnings", False)
        if stats["errors"] > 0 or (fail_on_warnings and stats["warnings"] > 0):
            sys.exit(1)

    def _generate_jsonl_report(self, violations, stats, options):
        """One JSON object per violation on stdout (or --output); the summary on stderr."""
        import json as _json

        to_file = get_option(options, "output")
        lines = (
            _json.dumps(normalize_for_json(item), ensure_ascii=False, default=str)
            for item in violations
        )
        if to_file:
            with open(to_file, "w", encoding="utf8") as out:
                for line in lines:
                    out.write(line + "\n")
        else:
            for line in lines:
                print(line)
        print(
            f"{stats['total_violations']} violations in {stats['total_records']} records "
            f"({stats['errors']} errors, {stats['warnings']} warnings)",
            file=sys.stderr,
        )
        fail_on_warnings = options.get("fail_on_warnings", False)
        if stats["errors"] > 0 or (fail_on_warnings and stats["warnings"] > 0):
            sys.exit(1)

    def _generate_json_report(
        self, violations, stats, violations_by_field, violations_by_rule, options
    ):
        """Generate JSON format validation report."""
        report = {
            "statistics": stats,
            "violations_by_field": {k: len(v) for k, v in violations_by_field.items()},
            "violations_by_rule": {k: len(v) for k, v in violations_by_rule.items()},
            "violations": violations[: options.get("max_violations", 100)],  # Limit for JSON output
        }

        from ..common.results import VALIDATE, dumps, envelope

        print(dumps(envelope(VALIDATE, report)))

        # Exit code based on failures
        fail_on_warnings = options.get("fail_on_warnings", False)
        if stats["errors"] > 0 or (fail_on_warnings and stats["warnings"] > 0):
            sys.exit(1)
