"""Data analysis and insights module.

This module provides data analysis capabilities including schema detection,
field type inference, and AI-powered documentation generation.

Note: Some functions have been optimized for performance (e.g., using sets
for key tracking), but further optimizations may be possible for very large datasets.
"""

import csv
import io
import json
import logging
import os
import sys
import tempfile
from collections import OrderedDict

import duckdb
import pandas as pd
import xlrd
import xmltodict
import yaml
from iterable.helpers.detect import detect_file_type
from openpyxl import load_workbook
from pydantic import BaseModel

from ..ai import AIService, get_ai_service, get_description, get_fields_info
from ..common.command_utils import (
    duckdb_read_csv_expr,
    get_iterable_options,
    iter_command_rows,
    resolve_csv_delimiter,
)
from ..common.engine_selector import is_format_supported_by_duckdb
from ..common.errors import ValidationError
from ..common.s3_iterable import open_iterable_with_s3
from ..common.schema_utils import duckdb_decompose
from ..common.tables import format_table
from ..constants import TEXT_DATA_TYPES
from ..formats.docx import analyze_docx
from ..utils import detect_encoding, get_dict_value, get_option

logger = logging.getLogger(__name__)

OBJECTS_ANALYZE_LIMIT = 10000

TABULAR_ITERABLE_TYPES = ["csv", "tsv", "json", "jsonl"]


def _selected_sheet_names(
    sheetnames: list[str], table_name: str | None = None, start_page: int = 0
) -> list[str]:
    """Restrict Excel sheets to a named table or 0-based page index."""
    if table_name:
        if table_name not in sheetnames:
            raise ValidationError(
                f"Unknown table or sheet {table_name!r}.",
                field="table",
                suggestions=list(sheetnames),
            )
        return [table_name]
    if start_page:
        if start_page < 0 or start_page >= len(sheetnames):
            raise ValidationError(
                f"Sheet index {start_page} is out of range (0-{len(sheetnames) - 1}).",
                field="start_page",
            )
        return [sheetnames[start_page]]
    return list(sheetnames)


DUCKDB_TYPES = ["VARCHAR", "DATE", "JSON", "BIGINT", "DOUBLE", "BOOLEAN"]


def _seek_dict_lists(data, level=0, path=None, candidates=None):
    """Seek list structures in dictionary recursively."""
    if candidates is None:
        candidates = OrderedDict()
    #    print(level, path, candidates)
    for key, value in data.items():
        if isinstance(value, list):
            isobjectlist = False
            for listitem in value[:20]:
                if isinstance(listitem, (dict, OrderedDict)):
                    isobjectlist = True
                    break
            if not isobjectlist:
                continue
            key = f"{path}.{key}" if path is not None else key
            if key not in candidates:
                candidates[key] = {"key": key, "num": len(value)}
        elif isinstance(value, (OrderedDict, dict)):
            res = _seek_dict_lists(value, level + 1, path + "." + key if path else key, candidates)
            for k, v in res.items():
                if k not in candidates.keys():
                    candidates[k] = v
        else:
            continue
    return candidates


def _seek_xml_lists(data, level=0, path=None, candidates=None):
    """Seek list structures in XML data recursively."""
    if candidates is None:
        candidates = OrderedDict()
    for key, value in data.items():
        if isinstance(value, list):
            key = f"{path}.{key}" if path is not None else key
            if key not in candidates:
                candidates[key] = {"key": key, "num": len(value)}
        elif isinstance(value, (OrderedDict, dict)):
            res = _seek_xml_lists(value, level + 1, path + "." + key if path else key, candidates)
            for k, v in res.items():
                if k not in candidates.keys():
                    candidates[k] = v
        else:
            continue
    return candidates


def _process_json_data(
    data,
    report,
    objects_limit,
    use_pandas,
    autodoc,
    lang,
    ai_service: AIService | None = None,
    *,
    stats: bool = True,
):
    """Process JSON data and add tables to report."""
    candidates = _seek_dict_lists(data, level=0)
    if len(candidates) == 1:
        fullkey = str(next(iter(candidates)))
        table = TableSchema(id=fullkey)
        objects = get_dict_value(data, keys=fullkey.split("."))[0]
        table = table_from_objects(
            objects,
            table_id=fullkey,
            objects_limit=objects_limit,
            use_pandas=use_pandas,
            filetype="jsonl",
            autodoc=autodoc,
            lang=lang,
            ai_service=ai_service,
            stats=stats,
        )
        report.tables.append(table)
        report.total_tables = len(report.tables)
        report.total_records = table.num_records
    elif len(candidates) > 1:
        total = 0
        for fullkey in candidates:
            table = TableSchema(id=fullkey)
            objects = get_dict_value(data, keys=fullkey.split("."))[0]
            table = table_from_objects(
                objects,
                table_id=fullkey,
                objects_limit=objects_limit,
                use_pandas=use_pandas,
                filetype="jsonl",
                autodoc=autodoc,
                lang=lang,
                ai_service=ai_service,
                stats=stats,
            )
            total += table.num_records
            report.tables.append(table)
        report.total_records = total
        report.total_tables = len(report.tables)


class FieldSchema(BaseModel):
    """Schema definition for a data field."""

    name: str
    ftype: str
    is_array: bool = False
    description: str | None = None
    unique_count: int | None = None
    total_count: int | None = None
    uniqueness_pct: float | None = None
    sem_type: str = None
    sem_url: str = None
    semantic_types: list[dict] | None = None
    pii: bool | None = None


class TableSchema(BaseModel):
    """Table schema definition."""

    num_records: int = -1
    num_cols: int = -1
    is_flat: bool = True
    id: str | None = None
    fields: list[FieldSchema] | None = []
    description: str | None = None


class ReportSchema(BaseModel):
    """Schema of the data file analysis results."""

    filename: str
    file_size: int
    file_type: str
    compression: str = None
    total_tables: int = 1
    total_records: int = -1
    tables: list[TableSchema] | None = []
    metadata: dict = {}
    success: bool = False
    error: str = None


MAX_SAMPLE_SIZE = 200
DELIMITED_FILES = ["csv", "tsv"]


def _field_from_column(column: list, include_stats: bool = True) -> FieldSchema:
    """Build a FieldSchema from a duckdb_decompose column row."""
    is_array = column[2] if isinstance(column[2], bool) else str(column[2]).lower() == "true"
    field = FieldSchema(name=column[0], ftype=column[1], is_array=is_array)
    if include_stats and len(column) > 5:
        try:
            field.unique_count = int(column[3])
            field.total_count = int(column[4])
            field.uniqueness_pct = float(column[5])
        except (ValueError, TypeError):
            pass
    return field


def _duckdb_sample_as_csv(query_str: str, limit: int = MAX_SAMPLE_SIZE) -> str:
    """Run a DuckDB query and return sample rows as CSV text with column headers."""
    df = duckdb.sql(query_str).fetchdf()
    if len(df) > limit:
        df = df.head(limit)
    return df.to_csv(index=False)


def _objects_are_dict_records(objects: list) -> bool:
    """Return True when objects look like JSON/XML record dicts."""
    if not objects:
        return False
    sample = objects[: min(len(objects), 20)]
    return all(isinstance(item, dict) for item in sample)


def _write_objects_tempfile(objects: list, filetype: str, objects_limit: int) -> str:
    """Write objects to an uncompressed temp file for DuckDB ingestion."""
    suffix = "." + filetype
    with tempfile.NamedTemporaryFile(
        suffix=suffix, mode="w", encoding="utf8", delete=False
    ) as tfile:
        if filetype == "csv":
            writer = csv.writer(tfile)
            writer.writerows(objects[:objects_limit])
        elif filetype in ("json", "jsonl"):
            for row in objects[:objects_limit]:
                tfile.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            raise ValueError(f"Unsupported temp file type: {filetype}")
        return tfile.name


def table_from_objects(
    objects: list,
    table_id: str,
    objects_limit: int,
    use_pandas: bool = False,
    filetype="csv",
    autodoc: bool = False,
    lang: str = "English",
    ai_service: AIService | None = None,
    stats: bool = True,
):
    """Reconstructs table schema from list of objects."""
    table = TableSchema(id=table_id)
    table.num_records = len(objects)
    if not objects:
        table.num_cols = 0
        return table

    if autodoc:
        sample = objects[:MAX_SAMPLE_SIZE]
        f = io.StringIO()
        if _objects_are_dict_records(sample):
            for row in sample:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        else:
            writer = csv.writer(f)
            writer.writerows(sample)
        table.description = get_description(f.getvalue(), language=lang, ai_service=ai_service)

    use_frame = use_pandas or _objects_are_dict_records(objects)
    if use_frame:
        df = pd.DataFrame(objects)
        columns_raw = duckdb_decompose(frame=df, path="*", limit=objects_limit, use_summarize=stats)
    else:
        tfile_name = _write_objects_tempfile(objects, filetype, objects_limit)
        try:
            columns_raw = duckdb_decompose(
                tfile_name,
                filetype=filetype,
                path="*",
                limit=objects_limit,
                use_summarize=stats,
            )
        finally:
            os.remove(tfile_name)
    is_flat = True
    table.num_cols = len(columns_raw)

    for column in columns_raw:
        field = _field_from_column(column, include_stats=stats)
        table.fields.append(field)
        if field.ftype == "STRUCT" or field.is_array:
            is_flat = False
        table.is_flat = is_flat
    table.num_records = len(objects)
    return table


def _analyze_iterable_file(
    filename: str,
    filetype: str,
    objects_limit: int,
    encoding: str | None,
    delimiter: str | None,
    use_pandas: bool,
    autodoc: bool,
    lang: str,
    ai_service: AIService | None,
    stats: bool,
    table_name: str | None = None,
    start_page: int = 0,
    trust: bool = False,
    options: dict | None = None,
) -> TableSchema:
    """Analyze a tabular file using the iterabledata row-by-row engine."""
    opts = {
        "encoding": encoding,
        "delimiter": delimiter,
        "trust": trust,
    }
    if table_name:
        opts["table"] = table_name
    if start_page:
        opts["start_page"] = start_page
    if options:
        for key in (
            "quotechar",
            "on_error",
            "error_log",
            "flatten_nested",
            "max_nested_depth",
            "keep_nested_parents",
        ):
            if options.get(key) is not None:
                opts[key] = options[key]
    iterableargs = get_iterable_options(opts)
    csv_delimiter = resolve_csv_delimiter(iterableargs, filename=filename, filetype=filetype)
    if csv_delimiter:
        iterableargs["delimiter"] = csv_delimiter

    objects = []
    total_records = 0
    with open_iterable_with_s3(filename, mode="r", iterableargs=iterableargs) as iterable:
        for item in iter_command_rows(iterable, opts):
            total_records += 1
            if len(objects) < objects_limit:
                if isinstance(item, dict):
                    objects.append(item)
                else:
                    objects.append({"value": item})

    table = table_from_objects(
        objects,
        table_id=os.path.basename(filename),
        objects_limit=objects_limit,
        use_pandas=use_pandas,
        filetype=filetype if filetype in ("json", "jsonl") else "jsonl",
        autodoc=autodoc,
        lang=lang,
        ai_service=ai_service,
        stats=stats,
    )
    table.num_records = total_records
    return table


def analyze(
    filename: str,
    filetype: str = None,
    compression: str = "raw",
    objects_limit: int = OBJECTS_ANALYZE_LIMIT,
    encoding: str = None,
    delimiter: str = None,
    scan: bool = True,
    stats: bool = True,
    engine: str = "auto",
    use_pandas: bool = False,
    ignore_errors: bool = True,
    autodoc: bool = False,
    lang: str = "English",
    ai_provider: str | None = None,
    ai_config: dict | None = None,
    table_name: str | None = None,
    start_page: int = 0,
    trust: bool = False,
    options: dict | None = None,
):
    """Analyzes any type of data file and provides meaningful insights.

    Args:
        filename: Path of the file to analyze.
        filetype: Format id; detected from the content and extension when omitted.
        compression: Compression codec of the file (``raw`` for none).
        objects_limit: Maximum number of records read to infer the structure.
        encoding: Text encoding; detected when omitted.
        use_pandas: Read tabular files with pandas instead of the streaming reader.
        ignore_errors: Skip unreadable records instead of failing.
        autodoc: Generate field and dataset descriptions with an AI provider.
        lang: Language of the generated descriptions.
        ai_provider: AI provider name (openai, openrouter, ollama, lmstudio, perplexity)
        ai_config: Optional AI configuration dictionary
        delimiter: CSV/TSV delimiter (auto-detected for CSV when omitted)
        scan: When False, return file metadata only (no table structure scan).
        stats: When True, include uniqueness stats from DuckDB summarize.
        engine: Processing engine ('auto', 'duckdb', or 'iterable').
        table_name: Named table or Excel sheet to analyze.
        start_page: 0-based Excel sheet index when ``table_name`` is omitted.
        trust: Acknowledge pickle deserialization risk.
        options: Extra reader options (flatten_nested, quotechar, on_error, ...).
    """
    options = options or {}
    fileext = filename.rsplit(".", 1)[-1].lower()
    filesize = os.path.getsize(filename)

    ftype = detect_file_type(filename)
    if filetype is None and ftype["success"]:
        filetype = ftype["datatype"].id()
        if ftype["codec"] is not None:
            compression = ftype["codec"].id()
    if filetype is None and fileext == "docx":
        filetype = "docx"

    report = ReportSchema(
        filename=filename, file_size=filesize, file_type=filetype, compression=compression
    )

    # Initialize AI service if autodoc is enabled
    ai_service = None
    if autodoc:
        try:
            config = ai_config or {}
            if ai_provider:
                config["provider"] = ai_provider
            ai_service = get_ai_service(provider=ai_provider, config=config)
            ai_service.fail_soft = True  # a failing request must not stop the report
        except Exception as e:  # noqa: BLE001 - the report is still useful without AI
            logger.warning("AI descriptions skipped: %s", str(e).rstrip("."))
            autodoc = False

    if filetype in TEXT_DATA_TYPES:
        if encoding is None:
            encoding_result = detect_encoding(filename)
            report.metadata["encoding"] = (
                encoding_result.get("encoding") if encoding_result else None
            )
        else:
            report.metadata["encoding"] = encoding
    if scan:
        use_duckdb = engine in ("auto", "duckdb") and is_format_supported_by_duckdb(
            filetype, compression
        )
        if engine in ("iterable", "python") or table_name or options.get("flatten_nested"):
            use_duckdb = False

        duckdb_failed = False
        if use_duckdb:
            try:
                iterableargs = {"delimiter": delimiter, "encoding": encoding}
                csv_delimiter = resolve_csv_delimiter(
                    iterableargs, filename=filename, filetype=filetype
                )
                text_ignore = ", ignore_errors=true" if ignore_errors else ""
                if filetype in ["json", "jsonl"]:
                    escaped = filename.replace("'", "''")
                    query_str = f"select count(*) from read_json('{escaped}'{text_ignore})"
                    num_records = duckdb.sql(query_str).fetchall()[0][0]
                elif filetype in ["csv", "tsv"]:
                    read_func = duckdb_read_csv_expr(
                        filename, csv_delimiter, ignore_errors=ignore_errors
                    )
                    query_str = f"select count(*) from {read_func}"
                    num_records = duckdb.sql(query_str).fetchall()[0][0]
                else:
                    escaped = filename.replace("'", "''")
                    query_str = f"select count(*) from '{escaped}'"
                    num_records = duckdb.sql(query_str).fetchall()[0][0]
                table = TableSchema(id=os.path.basename(filename))
                table.num_records = num_records
                report.tables = [table]
                report.total_records = table.num_records
                report.total_tables = 1

                columns_raw = duckdb_decompose(
                    filename,
                    filetype=filetype,
                    path="*",
                    limit=objects_limit,
                    use_summarize=stats,
                    ignore_errors=ignore_errors,
                    delimiter=csv_delimiter,
                )
                is_flat = True
                table.num_cols = len(columns_raw)
                for column in columns_raw:
                    field = _field_from_column(column, include_stats=stats)
                    table.fields.append(field)
                    if field.ftype == "STRUCT" or field.is_array:
                        is_flat = False
                table.is_flat = is_flat
                if filetype in ["csv", "tsv"]:
                    read_func = duckdb_read_csv_expr(
                        filename, csv_delimiter, ignore_errors=ignore_errors
                    )
                    query_str = f"select * from {read_func} limit {MAX_SAMPLE_SIZE}"
                elif filetype in ["json", "jsonl"]:
                    escaped = filename.replace("'", "''")
                    query_str = (
                        f"select * from read_json('{escaped}'{text_ignore}) limit {MAX_SAMPLE_SIZE}"
                    )
                else:
                    escaped = filename.replace("'", "''")
                    query_str = f"select * from '{escaped}' limit {MAX_SAMPLE_SIZE}"
                if autodoc:
                    table.description = get_description(
                        _duckdb_sample_as_csv(query_str),
                        language=lang,
                        ai_service=ai_service,
                    )
            except duckdb.Error as exc:
                if engine == "duckdb":
                    report.success = False
                    report.error = str(exc)
                    return report
                logger.warning("DuckDB analyze failed, falling back to iterable path: %s", exc)
                duckdb_failed = True
                report.tables = []

        if not use_duckdb or duckdb_failed:
            if engine == "duckdb" and not duckdb_failed:
                report.success = False
                report.error = (
                    f"Not supported file type {report.file_type} "
                    f"or compression {report.compression}"
                )
            elif filetype in TABULAR_ITERABLE_TYPES:
                table = _analyze_iterable_file(
                    filename,
                    filetype=filetype,
                    objects_limit=objects_limit,
                    encoding=encoding,
                    delimiter=delimiter,
                    use_pandas=use_pandas,
                    autodoc=autodoc,
                    lang=lang,
                    ai_service=ai_service,
                    stats=stats,
                    table_name=table_name,
                    start_page=start_page,
                    trust=trust,
                    options=options,
                )
                report.tables = [table]
                report.total_records = table.num_records
                report.total_tables = 1
            elif fileext == "docx":
                docx_tables = analyze_docx(filename, extract_data=True)
                total = 0
                for dtable in docx_tables:
                    table = table_from_objects(
                        dtable["data"],
                        table_id=str(dtable["id"]),
                        objects_limit=objects_limit,
                        use_pandas=use_pandas,
                        filetype="csv",
                        autodoc=autodoc,
                        lang=lang,
                        ai_service=ai_service,
                        stats=stats,
                    )
                    total += table.num_records
                    report.tables.append(table)
                report.total_records = total
                report.total_tables = len(report.tables)
            elif filetype == "xlsx":
                wb = load_workbook(filename, read_only=True, data_only=True)
                total = 0
                for sheetname in _selected_sheet_names(list(wb.sheetnames), table_name, start_page):
                    sheet = wb[sheetname]
                    objects = []
                    max_num = min(objects_limit, sheet.max_row or 0)
                    for row in sheet.iter_rows(max_row=max_num, values_only=True):
                        objects.append([str(cell) if cell is not None else "" for cell in row])
                    table = table_from_objects(
                        objects,
                        table_id=sheetname,
                        objects_limit=objects_limit,
                        use_pandas=use_pandas,
                        filetype="csv",
                        autodoc=autodoc,
                        lang=lang,
                        ai_service=ai_service,
                        stats=stats,
                    )
                    total += table.num_records
                    report.tables.append(table)
                report.total_records = total
                report.total_tables = len(report.tables)
            elif filetype == "xls":
                wb = xlrd.open_workbook(filename)
                total = 0
                for sheetname in _selected_sheet_names(
                    list(wb.sheet_names()), table_name, start_page
                ):
                    sheet = wb.sheet_by_name(sheetname)
                    objects = []
                    max_num = objects_limit if objects_limit < sheet.nrows else sheet.nrows
                    for n in range(0, max_num):
                        tmp = []
                        for i in range(0, sheet.ncols):
                            cell_value = sheet.cell_value(n, i)
                            get_col = str(cell_value)
                            tmp.append(get_col)
                        objects.append(tmp)
                    table = table_from_objects(
                        objects,
                        table_id=sheetname,
                        objects_limit=objects_limit,
                        use_pandas=use_pandas,
                        filetype="csv",
                        autodoc=autodoc,
                        lang=lang,
                        ai_service=ai_service,
                        stats=stats,
                    )
                    report.tables.append(table)
                    total += table.num_records
                report.total_records = total
                report.total_tables = len(report.tables)
            elif filetype == "xml":
                fileobj = None
                codec = None
                if ftype.get("success") and ftype.get("codec") is not None:
                    codec = ftype["codec"](filename, open_it=True)
                    fileobj = codec.fileobj()
                if fileobj is None:
                    with open(filename, "rb") as f:
                        data = xmltodict.parse(f, process_namespaces=False)
                else:
                    data = xmltodict.parse(fileobj, process_namespaces=False)
                candidates = _seek_xml_lists(data, level=0)
                if len(candidates) == 1:
                    fullkey = str(next(iter(candidates)))
                    table = TableSchema(id=fullkey)
                    objects = get_dict_value(data, keys=fullkey.split("."))[0]
                    table = table_from_objects(
                        objects,
                        table_id=fullkey,
                        objects_limit=objects_limit,
                        use_pandas=use_pandas,
                        filetype="jsonl",
                        autodoc=autodoc,
                        lang=lang,
                        ai_service=ai_service,
                        stats=stats,
                    )
                    report.tables.append(table)
                    report.total_tables = len(report.tables)
                    report.total_records = table.num_records
                elif len(candidates) > 1:
                    total = 0
                    for fullkey in candidates:
                        table = TableSchema(id=fullkey)
                        objects = get_dict_value(data, keys=fullkey.split("."))[0]
                        table = table_from_objects(
                            objects,
                            table_id=fullkey,
                            objects_limit=objects_limit,
                            use_pandas=use_pandas,
                            filetype="jsonl",
                            autodoc=autodoc,
                            lang=lang,
                            ai_service=ai_service,
                            stats=stats,
                        )
                        total += table.num_records
                        report.tables.append(table)
                    report.total_records = total
                    report.total_tables = len(report.tables)
                if codec is not None:
                    codec.close()
                elif fileobj is not None:
                    fileobj.close()
            elif filetype == "json":
                fileobj = None
                codec = None
                if ftype.get("success") and ftype.get("codec") is not None:
                    codec = ftype["codec"](filename, open_it=True)
                    fileobj = codec.fileobj()
                if fileobj is None:
                    with open(filename, "rb") as f:
                        data = json.load(f)
                else:
                    data = json.load(fileobj)
                _process_json_data(
                    data,
                    report,
                    objects_limit,
                    use_pandas,
                    autodoc,
                    lang,
                    ai_service,
                    stats=stats,
                )
                if codec is not None:
                    codec.close()
                elif fileobj is not None:
                    fileobj.close()
            elif table_name:
                table = _analyze_iterable_file(
                    filename,
                    filetype=filetype,
                    objects_limit=objects_limit,
                    encoding=encoding,
                    delimiter=delimiter,
                    use_pandas=use_pandas,
                    autodoc=autodoc,
                    lang=lang,
                    ai_service=ai_service,
                    stats=stats,
                    table_name=table_name,
                    start_page=start_page,
                    trust=trust,
                    options=options,
                )
                report.tables = [table]
                report.total_records = table.num_records
                report.total_tables = 1

    if autodoc and report.total_tables > 0:
        for table in report.tables:
            fields = []
            for column in table.fields:
                fields.append(column.name)
            descriptions = get_fields_info(fields, language=lang, ai_service=ai_service)
            for column in table.fields:
                if column.name in descriptions:
                    column.description = descriptions[column.name]
    if report.error is None:
        report.success = True
    return report


def _format_file_size(size_bytes):
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def _format_number(num):
    """Format number with commas for readability."""
    if num is None or num == -1:
        return "N/A"
    return f"{num:,}"


def _resolve_analyze_outtype(options: dict) -> str:
    """Resolve analyze output format from flags, config, or the output path."""
    value = (get_option(options, "format_out") or get_option(options, "outtype") or "").lower()
    value = value.strip()
    if value:
        return value
    output = get_option(options, "output")
    if output:
        lower = str(output).lower()
        if lower.endswith(".json"):
            return "json"
        if lower.endswith((".yaml", ".yml")):
            return "yaml"
        if lower.endswith((".md", ".markdown")):
            return "markdown"
    return "text"


def _md_cell(value) -> str:
    text = "-" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", " ")


def _md_table(headers: list[str], rows: list[list]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_md_cell(cell) for cell in row) + " |")
    return "\n".join(lines)


def _analysis_markdown(report, options) -> str:
    """Render an analysis report as Markdown."""
    parts = [
        "# Analysis report",
        "",
        "## File information",
        "",
        _md_table(
            ["Attribute", "Value"],
            [
                ["Filename", report.filename],
                ["File size", _format_file_size(report.file_size)],
                ["File type", report.file_type or "N/A"],
                ["Compression", report.compression or "None"],
                ["Total tables", _format_number(report.total_tables)],
                ["Total records", _format_number(report.total_records)],
                *[[k.replace("_", " ").title(), v] for k, v in (report.metadata or {}).items()],
            ],
        ),
        "",
    ]
    if not report.tables:
        return "\n".join(parts).rstrip() + "\n"

    show_stats = options.get("stats", True) and any(
        f.unique_count is not None for t in report.tables for f in (t.fields or [])
    )
    headers = ["Field Name", "Type", "Is Array"]
    if show_stats:
        headers.extend(["Unique", "Total", "Unique %"])
    headers.append("Description")

    parts.append("## Table structures")
    parts.append("")
    for rtable in report.tables:
        title = rtable.id or "table"
        parts.append(f"### {title}")
        parts.append("")
        parts.append(
            f"Records: {_format_number(rtable.num_records)} · "
            f"Columns: {_format_number(rtable.num_cols)} · "
            f"Structure: {'Flat' if rtable.is_flat else 'Nested'}"
        )
        parts.append("")
        rows = []
        for field in rtable.fields or []:
            row = [field.name, field.ftype, "Yes" if field.is_array else "No"]
            if show_stats:
                row.extend(
                    [
                        _format_number(field.unique_count),
                        _format_number(field.total_count),
                        (
                            f"{field.uniqueness_pct:.2f}%"
                            if field.uniqueness_pct is not None
                            else "N/A"
                        ),
                    ]
                )
            row.append(field.description or "-")
            rows.append(row)
        parts.append(_md_table(headers, rows))
        parts.append("")
        if rtable.description:
            parts.append(rtable.description.strip())
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _write_analysis_output(report, options, output_stream):
    """Write analysis report to output stream in the specified format."""
    if options["outtype"] == "json":
        from ..common.results import ANALYZE, dumps, envelope

        output_stream.write(dumps(envelope(ANALYZE, report.model_dump())))
        output_stream.write("\n")
    elif options["outtype"] == "yaml":
        yaml_output = yaml.dump(report.model_dump(), Dumper=yaml.Dumper)
        output_stream.write(yaml_output)
    elif options["outtype"] == "markdown":
        output_stream.write(_analysis_markdown(report, options))
    else:
        # Text output format
        # Print header
        print("=" * 70, file=output_stream)
        print("ANALYSIS REPORT", file=output_stream)
        print("=" * 70, file=output_stream)
        print(file=output_stream)

        # File information section
        print("File Information", file=output_stream)
        print("-" * 70, file=output_stream)
        headers = ["Attribute", "Value"]
        reptable = []
        reptable.append(["Filename", str(report.filename)])
        reptable.append(["File size", _format_file_size(report.file_size)])
        reptable.append(["File type", report.file_type or "N/A"])
        reptable.append(["Compression", str(report.compression) if report.compression else "None"])
        reptable.append(["Total tables", _format_number(report.total_tables)])
        reptable.append(["Total records", _format_number(report.total_records)])
        for k, v in report.metadata.items():
            reptable.append([k.replace("_", " ").title(), str(v)])
        print(format_table(reptable, headers, "grid"), file=output_stream)
        print(file=output_stream)

        # Tables section
        if report.tables:
            print("=" * 70, file=output_stream)
            print("TABLE STRUCTURES", file=output_stream)
            print("=" * 70, file=output_stream)
            print(file=output_stream)

            show_stats = options.get("stats", True) and any(
                f.unique_count is not None for t in report.tables for f in (t.fields or [])
            )
            tabheaders = ["Field Name", "Type", "Is Array"]
            if show_stats:
                tabheaders.extend(["Unique", "Total", "Unique %"])
            tabheaders.append("Description")
            for idx, rtable in enumerate(report.tables, 1):
                if len(report.tables) > 1:
                    print(f"Table {idx}: {rtable.id}", file=output_stream)
                else:
                    print(f"Table: {rtable.id}", file=output_stream)
                print("-" * 70, file=output_stream)
                print(f"  Records: {_format_number(rtable.num_records)}", file=output_stream)
                print(f"  Columns: {_format_number(rtable.num_cols)}", file=output_stream)
                print(f"  Structure: {'Flat' if rtable.is_flat else 'Nested'}", file=output_stream)
                print(file=output_stream)

                table = []
                for field in rtable.fields:
                    desc = field.description if field.description else "-"
                    row = [field.name, field.ftype, "Yes" if field.is_array else "No"]
                    if show_stats:
                        row.extend(
                            [
                                _format_number(field.unique_count),
                                _format_number(field.total_count),
                                (
                                    f"{field.uniqueness_pct:.2f}%"
                                    if field.uniqueness_pct is not None
                                    else "N/A"
                                ),
                            ]
                        )
                    row.append(desc)
                    table.append(row)
                print(format_table(table, tabheaders, "grid"), file=output_stream)

                if rtable.description:
                    print(file=output_stream)
                    print("Summary:", file=output_stream)
                    print("-" * 70, file=output_stream)
                    # Wrap description text for better readability
                    desc_lines = rtable.description.split("\n")
                    for line in desc_lines:
                        if line.strip():
                            print(f"  {line.strip()}", file=output_stream)

                if idx < len(report.tables):
                    print(file=output_stream)
                    print(file=output_stream)


class Analyzer:
    """Data analysis handler."""

    def __init__(self):
        pass

    def analyze(self, filename, options):
        """Analyze a data file and return its parameters."""
        from ..common.errors import FileNotFoundError, PermissionError, find_similar_files
        from ..common.path_utils import validate_file_path

        try:
            validate_file_path(filename, check_read=True)
        except FileNotFoundError as e:
            suggestions = find_similar_files(filename)
            raise FileNotFoundError(filename, suggestions) from e
        except PermissionError as e:
            raise PermissionError(filename, operation="read") from e

        report = analyze(
            filename,
            encoding=options.get("encoding"),
            delimiter=options.get("delimiter"),
            objects_limit=options.get("objects_limit", OBJECTS_ANALYZE_LIMIT),
            scan=options.get("scan", True),
            stats=options.get("stats", True),
            engine=get_option(options, "engine") or "auto",
            use_pandas=options.get("use_pandas") or False,
            ignore_errors=options.get("ignore_errors", True),
            autodoc=options.get("autodoc") or False,
            lang=options.get("lang") or "English",
            ai_provider=options.get("ai_provider"),
            ai_config=options.get("ai_config"),
            table_name=options.get("table"),
            start_page=options.get("start_page") or 0,
            trust=bool(options.get("trust")),
            options=options,
        )

        options = dict(options)
        options["outtype"] = _resolve_analyze_outtype(options)

        # Determine output destination
        output_file = options.get("output")

        if output_file:
            # Use context manager for file output
            with open(output_file, "w", encoding="utf8") as output_stream:
                _write_analysis_output(report, options, output_stream)
        else:
            # Write to stdout
            _write_analysis_output(report, options, sys.stdout)
