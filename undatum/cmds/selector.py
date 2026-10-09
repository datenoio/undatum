"""Data selection and filtering module."""

import itertools
import logging
import os
from typing import Any

from ..common.command_utils import (
    ITERABLE_OPTIONS_KEYS,  # noqa: F401
    duckdb_read_expr,
    force_iterable_if_table,
    get_iterable_options,
    iter_command_rows,
    quote_sql_identifier,
)
from ..common.duckdb_config import create_duckdb_connection, get_duckdb_config_from_options
from ..common.engine_selector import detect_engine
from ..common.errors import (
    FileNotFoundError,
    FormatError,
    PermissionError,
    ValidationError,
    find_similar_files,
)
from ..common.filter import match_filter, translate_filter_to_sql
from ..common.path_utils import validate_file_path
from ..common.s3_iterable import open_path as open_iterable
from ..common.writer import (
    RecordSink,
    StdoutSink,
    duckdb_copy_to_file,
    emit_records,
    resolve_output_format,
)
from ..ops import write_rows
from ..utils import (
    dict_generator,
    field_values,
    get_file_type,
    get_option,
    select_fields,
)

logger = logging.getLogger(__name__)

LINEEND = b"\n"
SELECT_BATCH_SIZE = 1000


class _SelectOutput:
    """Unified output writer for select command (file or stdout)."""

    def __init__(self, to_file, format_out, fields):
        self._to_file = to_file
        self._format_out = format_out
        self._fields = fields
        self._out_iterable = None
        self._stdout = None

    def write_batch(self, items):
        if not items:
            return
        if self._to_file:
            if self._out_iterable is None:
                self._out_iterable = RecordSink(
                    self._to_file, fieldnames=self._fields, format_out=self._format_out or None
                )
            self._out_iterable.write_batch(items)
            return
        if self._stdout is None:
            from ..common.stdio import stdout_format

            self._stdout = StdoutSink(
                self._format_out or stdout_format.get() or "jsonl", fieldnames=self._fields
            )
        self._stdout.write_batch(items)

    def close(self):
        if self._to_file and self._out_iterable is None:
            # No rows matched: still publish an empty file with the selected columns.
            self._out_iterable = RecordSink(
                self._to_file, fieldnames=self._fields, format_out=self._format_out or None
            )
        if self._out_iterable is not None:
            self._out_iterable.close()
            self._out_iterable = None
        if self._stdout is not None:
            self._stdout.close()
            self._stdout = None

    def abort(self):
        if self._out_iterable is not None:
            self._out_iterable.abort()
            self._out_iterable = None


def _rows_as_dicts(rows, fields: list[str]):
    """Turn engine results (strings, tuples or dicts) into dicts keyed by ``fields``."""
    for row in rows:
        if isinstance(row, dict):
            yield row
        elif isinstance(row, (list, tuple)):
            yield dict(zip(fields, row, strict=False))
        else:
            yield {fields[0]: row}


def _has_nested_fields(fields: list[str]) -> bool:
    return any("." in field for field in fields)


def _build_select_query(fields: list[str], source: str, filter_sql: str | None = None) -> str:
    field_sql = ", ".join(quote_sql_identifier(field) for field in fields)
    query = f"SELECT {field_sql} FROM {source}"
    if filter_sql:
        query = f"{query} WHERE {filter_sql}"
    return query


def _duckdb_copy_select(conn, query: str, to_file: str, to_type: str) -> bool:
    """Write select results directly to file via DuckDB COPY. Returns True if handled."""
    return duckdb_copy_to_file(conn, query, to_file)


def _engine_for_filter(detected_engine: str, filter_expr, command: str):
    """Keep DuckDB when the filter translates to SQL; otherwise fall back to iterable."""
    filter_sql = None
    if detected_engine == "duckdb" and filter_expr:
        filter_sql = translate_filter_to_sql(filter_expr)
        if filter_sql is None:
            logger.info("%s: filter not translatable to SQL, falling back to iterable", command)
            return "iterable", None
    return detected_engine, filter_sql


def get_iterable_fields_uniq(iterable, fields, dolog=False, dq_instance=None, filter_expr=None):  # pylint: disable=unused-argument
    """Returns all uniq values of the fields of iterable dictionary."""
    # dq_instance parameter kept for backward compatibility (no longer used)
    n = 0
    uniqval = []
    for row in iterable:
        n += 1
        if dolog and n % 1000 == 0:
            logger.debug("uniq: processing %d records", n)
        if filter_expr is not None:
            if not match_filter(row, filter_expr):
                continue
        try:
            allvals = []
            for field in fields:
                allvals.append(field_values(row, field))

            for n1, _ in enumerate(allvals[0]):
                k = []
                for n2, _ in enumerate(allvals):
                    k.append(str(allvals[n2][n1]))
                if k not in uniqval:
                    uniqval.append(k)
        except KeyError:
            pass
    return uniqval


def get_duckdb_fields_uniq(
    filename,
    fields,
    filetype=None,
    duckdb_config=None,
    dolog=False,
    dq_instance=None,
    filter_sql=None,
):  # pylint: disable=unused-argument
    """Returns all uniq values of the fields of the filename using DuckDB."""
    # dq_instance parameter kept for backward compatibility (no longer used)
    if duckdb_config is None:
        duckdb_config = {}

    conn = create_duckdb_connection(**duckdb_config)

    # Determine input format and build appropriate read expression
    source_type = filetype or get_file_type(filename) or "csv"
    if source_type == "csv":
        read_expr = f"read_csv_auto('{filename}', all_varchar=true)"
    elif source_type in ("json", "jsonl"):
        read_expr = f"read_json_auto('{filename}')"
    elif source_type == "parquet":
        read_expr = f"read_parquet('{filename}')"
    else:
        conn.close()
        raise ValueError(f"Unsupported file type for DuckDB: {source_type}")

    fieldstext = ",".join(quote_sql_identifier(field) for field in fields)
    query = f"SELECT DISTINCT {fieldstext} FROM {read_expr}"
    if filter_sql:
        query = f"{query} WHERE {filter_sql}"
    if dolog:
        logger.info(query)

    try:
        relation = conn.execute(query)
        uniqval = relation.fetchall()
        conn.close()
        return uniqval
    except Exception:
        conn.close()
        raise


def get_iterable_fields_freq(
    iterable, fields, dolog=False, filter_expr=None, dq_instance=None, threads=None
):  # pylint: disable=unused-argument
    """Iterates and returns most frequent values.

    Args:
        iterable: Record iterable.
        fields: Field names to count.
        dolog: Emit progress logs.
        filter_expr: Optional filter expression.
        dq_instance: Unused; kept for backward compatibility.
        threads: When > 1, accumulate frequencies in a process pool.
    """
    use_parallel = bool(threads) and int(threads) > 1
    if use_parallel:
        from ..common.chunked_io import chunked_reader
        from ..common.parallel import parallel_process_chunks
        from ..common.parallel_workers import frequency_chunk, merge_frequency_partials

        def _payloads():
            for chunk in chunked_reader(iterable, chunk_size=5000):
                yield (list(chunk), fields, filter_expr)

        partials = list(
            parallel_process_chunks(
                frequency_chunk,
                _payloads(),
                num_threads=int(threads),
                use_processes=True,
                preserve_order=False,
            )
        )
        valuedict = merge_frequency_partials(partials)
        items = []
        for k, v in valuedict.items():
            row = k.split("\t")
            row.append(v)
            items.append(row)
        items.sort(key=lambda x: x[-1], reverse=True)
        return items

    n = 0
    valuedict = {}
    items = []
    for r in iterable:
        n += 1
        if dolog and n % 10000 == 0:
            logger.info("frequency: processing %d records", n)
        if filter_expr is not None:
            if not match_filter(r, filter_expr):
                continue
        try:
            allvals = []
            for field in fields:
                allvals.append(field_values(r, field))

            for n1, _ in enumerate(allvals[0]):
                k = []
                for n2, _ in enumerate(allvals):
                    k.append(str(allvals[n2][n1]))
                kx = "\t".join(k)
                v = valuedict.get(kx, 0)
                valuedict[kx] = v + 1
        except KeyError:
            pass
    for k, v in valuedict.items():
        row = k.split("\t")
        row.append(v)
        items.append(row)
    items.sort(key=lambda x: x[-1], reverse=True)
    return items


def get_duckdb_fields_freq(
    filename,
    fields,
    filetype=None,
    duckdb_config=None,
    dolog=False,
    dq_instance=None,
    filter_sql=None,
):  # pylint: disable=unused-argument
    """Returns frequencies for the fields of the filename using DuckDB."""
    # dq_instance parameter kept for backward compatibility (no longer used)
    if duckdb_config is None:
        duckdb_config = {}

    conn = create_duckdb_connection(**duckdb_config)

    # Determine input format and build appropriate read expression
    source_type = filetype or get_file_type(filename) or "csv"
    if source_type == "csv":
        read_expr = f"read_csv_auto('{filename}', all_varchar=true)"
    elif source_type in ("json", "jsonl"):
        read_expr = f"read_json_auto('{filename}')"
    elif source_type == "parquet":
        read_expr = f"read_parquet('{filename}')"
    else:
        conn.close()
        raise ValueError(f"Unsupported file type for DuckDB: {source_type}")

    fieldstext = ",".join(quote_sql_identifier(field) for field in fields)
    query = f"SELECT {fieldstext}, count(*) as c FROM {read_expr}"
    if filter_sql:
        query = f"{query} WHERE {filter_sql}"
    query = f"{query} GROUP BY {fieldstext} ORDER BY c DESC"
    if dolog:
        logger.info(query)

    try:
        relation = conn.execute(query)
        uniqval = relation.fetchall()
        conn.close()
        return uniqval
    except Exception:
        conn.close()
        raise


def header_names(fromfile: str, options: dict[str, Any] | None = None) -> list[str]:
    """Field names of a file in first-seen (file column) order.

    Args:
        fromfile: Input path.
        options: Reader options; ``limit`` caps the records read, ``flatten_nested``
            reports dotted paths of nested fields as they are unfolded.

    Returns:
        Field names; nested fields as dotted paths.
    """
    options = options or {}
    limit = get_option(options, "limit")
    iterable = open_iterable(fromfile, mode="r", iterableargs=get_iterable_options(options))
    try:
        # A dict keeps first-seen order (file column order) with O(1) membership.
        keys_seen: dict[str, None] = {}
        n = 0
        for item in iter_command_rows(iterable, options):
            if limit and n > limit:
                break
            n += 1
            if options.get("flatten_nested") and isinstance(item, dict):
                keys_seen.update(dict.fromkeys(item.keys()))
                continue
            for path in dict_generator(item):
                keys_seen.setdefault(".".join(path[:-1]), None)
    finally:
        iterable.close()
    return list(keys_seen)


def _split_format(source: Any, format_out: str | None) -> str:
    """Output format of ``split``: ``format_out``, else the input's format when writable."""
    from ..common.writer import resolve_output_format

    candidate = (format_out or source.format_id or "jsonl").lower()
    try:
        return resolve_output_format(f"part.{candidate}", candidate)
    except FormatError:
        if format_out:
            raise
        return "jsonl"


class Selector:
    """Data selection and filtering handler."""

    def __init__(self):
        pass

    def uniq(self, fromfile, options=None):
        """Extracts unique values by field."""
        if options is None:
            options = {}
        logger.debug("Processing %s", fromfile)
        iterableargs = get_iterable_options(options)
        filetype = get_option(options, "filetype")
        to_file = get_option(options, "output")
        engine = get_option(options, "engine")
        format_out = (get_option(options, "format_out") or "").lower()
        if to_file:
            resolve_output_format(to_file, format_out or None)
        fields = options["fields"].split(",")
        filter_expr = get_option(options, "filter")
        detected_engine = detect_engine(fromfile, engine, filetype, operation="uniq")
        detected_engine = force_iterable_if_table(options, detected_engine)
        detected_engine, filter_sql = _engine_for_filter(detected_engine, filter_expr, "uniq")
        uniqval = None
        if detected_engine == "duckdb":
            try:
                duckdb_config = get_duckdb_config_from_options(options)
                uniqval = get_duckdb_fields_uniq(
                    fromfile,
                    fields,
                    filetype=filetype,
                    duckdb_config=duckdb_config,
                    dolog=True,
                    filter_sql=filter_sql,
                )
            except Exception as e:
                logger.warning(f"DuckDB uniq failed, falling back to iterable: {e}")
                detected_engine = "iterable"

        if detected_engine == "iterable":
            iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
            try:
                logger.info("uniq: looking for fields: {}".format(options["fields"]))
                uniqval = get_iterable_fields_uniq(
                    iter_command_rows(iterable, options),
                    fields,
                    dolog=True,
                    filter_expr=filter_expr,
                )
            finally:
                iterable.close()
        elif uniqval is None:
            raise ValidationError(
                f"Unsupported engine '{detected_engine}'",
                field="engine",
                suggestions=["auto", "duckdb", "python"],
            )
        logger.debug(f"{len(uniqval)} unique values found")
        emit_records(
            _rows_as_dicts(uniqval, fields),
            to_file,
            fieldnames=fields,
            format_out=format_out or None,
            stdout_format=format_out or "csv",
        )

    def headers(self, fromfile, options=None):
        """Print field names in file order (one per line, or JSON with ``format_out``)."""
        if options is None:
            options = {}
        keys = header_names(fromfile, options)
        output = get_option(options, "output")
        format_out = (get_option(options, "format_out") or "").lower()
        if not format_out and output and str(output).lower().endswith(".json"):
            format_out = "json"
        if format_out == "json":
            from ..common.results import HEADERS, emit

            emit(HEADERS, {"file": fromfile, "fields": keys}, output=output)
            return
        if output:
            with open(output, "w", encoding=get_option(options, "encoding")) as f:
                f.write("\n".join(keys))
        else:
            for x in keys:
                print(x.encode("utf8").decode("utf8", "ignore"))

    def frequency(self, fromfile, options=None):
        """Calculates frequency of the values in the file."""
        if options is None:
            options = {}
        logger.debug("Processing %s", fromfile)
        iterableargs = get_iterable_options(options)
        filetype = get_option(options, "filetype")
        to_file = get_option(options, "output")
        engine = get_option(options, "engine")
        format_out = (get_option(options, "format_out") or "").lower()
        if to_file:
            resolve_output_format(to_file, format_out or None)
        fields = options["fields"].split(",")
        filter_expr = get_option(options, "filter")
        detected_engine = detect_engine(fromfile, engine, filetype, operation="frequency")
        detected_engine = force_iterable_if_table(options, detected_engine)
        detected_engine, filter_sql = _engine_for_filter(detected_engine, filter_expr, "frequency")
        items = []
        if detected_engine == "duckdb":
            try:
                duckdb_config = get_duckdb_config_from_options(options)
                items = get_duckdb_fields_freq(
                    fromfile,
                    fields=fields,
                    filetype=filetype,
                    duckdb_config=duckdb_config,
                    dolog=True,
                    filter_sql=filter_sql,
                )
            except Exception as e:
                logger.warning(f"DuckDB frequency failed, falling back to iterable: {e}")
                detected_engine = "iterable"
        if detected_engine == "iterable":
            iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
            try:
                if iterable is not None:
                    items = get_iterable_fields_freq(
                        iter_command_rows(iterable, options),
                        fields,
                        dolog=True,
                        filter_expr=options.get("filter"),
                        threads=get_option(options, "threads"),
                    )
                else:
                    raise FormatError(fromfile, str(filetype or "unknown"))
            finally:
                iterable.close()
        elif not items and detected_engine != "duckdb":
            raise ValidationError(
                f"Unsupported engine '{detected_engine}'",
                field="engine",
                suggestions=["auto", "duckdb", "python"],
            )
        logger.debug(f"frequency: {len(items)} unique values found")
        fields.append("count")
        emit_records(
            _rows_as_dicts(items, fields),
            to_file,
            fieldnames=fields,
            format_out=format_out or None,
            stdout_format=format_out or "csv",
        )

    def select(self, fromfile, options=None):
        """Select or re-order columns from file."""
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

        iterableargs = get_iterable_options(options)
        to_file = get_option(options, "output")
        format_out = get_option(options, "format_out")
        filetype = get_option(options, "format_in")
        engine = get_option(options, "engine")
        fields_value = get_option(options, "fields")
        from ..ops.expr import where_steps

        steps = where_steps(options)
        if steps:
            from ..io import open_source
            from ..ops import SelectConfig, run_steps

            chosen = [f.strip() for f in (fields_value or "").split(",") if f.strip()]
            cfg = SelectConfig(fields=tuple(chosen), filter=get_option(options, "filter"))
            if cfg.fields or cfg.filter:
                steps = [*steps, ("select", cfg)]
            run_steps(
                steps,
                open_source(fromfile, options),
                to_file,
                engine=engine or "auto",
                format_out=format_out,
            )
            return
        if not fields_value:
            raise ValidationError(
                "select requires --fields, --where or --add (fields: comma-separated names)",
                field="fields",
            )
        fields = [field.strip() for field in fields_value.split(",") if field.strip()]
        if not fields:
            raise ValidationError(
                "select requires at least one field name in 'fields'", field="fields"
            )

        to_type = None
        if to_file:
            to_type = resolve_output_format(to_file, format_out or None)

        fields_list = [field.split(".") for field in fields]
        output = _SelectOutput(to_file, format_out, fields)

        filter_expr = get_option(options, "filter")
        detected_engine = detect_engine(fromfile, engine, filetype, operation="select")
        detected_engine = force_iterable_if_table(options, detected_engine)
        filter_sql = None

        if _has_nested_fields(fields):
            logger.info("select: nested fields require iterable engine")
            detected_engine = "iterable"
        elif detected_engine == "duckdb" and filter_expr:
            filter_sql = translate_filter_to_sql(filter_expr)
            if filter_sql is None:
                logger.info("select: filter not translatable to SQL, falling back to iterable")
                detected_engine = "iterable"

        try:
            flatten_nested = bool(options.get("flatten_nested"))
            n = 0
            batch = []
            if detected_engine == "duckdb":
                try:
                    duckdb_config = get_duckdb_config_from_options(options)
                    conn = create_duckdb_connection(**duckdb_config)
                    source = duckdb_read_expr(fromfile, filetype, iterableargs, all_varchar=True)
                    query = _build_select_query(fields, source, filter_sql)

                    if to_file and _duckdb_copy_select(conn, query, to_file, to_type):
                        conn.close()
                        logger.info("select: completed using DuckDB COPY")
                        return

                    relation = conn.execute(query)
                    while True:
                        rows = relation.fetchmany(SELECT_BATCH_SIZE)
                        if not rows:
                            break
                        batch = [dict(zip(fields, row, strict=False)) for row in rows]
                        n += len(batch)
                        output.write_batch(batch)
                    conn.close()
                except Exception as exc:
                    if n > 0:
                        logger.error("select: DuckDB failed after output (%s)", exc)
                        raise
                    logger.warning("select: DuckDB failed (%s), falling back to iterable", exc)
                    detected_engine = "iterable"

            if detected_engine == "iterable":
                iterable = open_iterable(fromfile, mode="r", iterableargs=iterableargs)
                try:
                    for r in iter_command_rows(iterable, options):
                        n += 1
                        if filter_expr is not None:
                            if not match_filter(r, filter_expr):
                                continue
                        if flatten_nested:
                            r_selected = {field: r[field] for field in fields if field in r}
                        else:
                            r_selected = select_fields(r, fields_list)
                        batch.append(r_selected)
                        if len(batch) >= SELECT_BATCH_SIZE:
                            output.write_batch(batch)
                            batch = []
                    if batch:
                        output.write_batch(batch)
                finally:
                    iterable.close()

        except BaseException:
            output.abort()
            raise
        output.close()

    def split(self, fromfile, options=None):
        """Split a file into chunks of ``chunksize`` records, or into one file per value.

        With ``fields`` every distinct value combination gets its own file
        (``<dirname>/<value>.<ext>``) or, with ``hive``, its own directory
        (``<dirname>/<field>=<value>/data_0.<ext>``). Output files use ``format_out`` or the
        input's format; at most ``max_open_files`` are open at once.
        """
        from ..io import RowSource
        from ..io.partition import DEFAULT_MAX_OPEN_FILES, PartitionedWriter

        if options is None:
            options = {}
        validate_file_path(fromfile, check_read=True)
        source = RowSource(fromfile, options)
        format_out = _split_format(source, get_option(options, "format_out"))
        extension = format_out + (".gz" if options.get("gzipfile") else "")
        filter_expr = get_option(options, "filter")
        rows: Any = (
            row
            for row in source
            if filter_expr is None or (isinstance(row, dict) and match_filter(row, filter_expr))
        )
        fields_value = get_option(options, "fields")
        dirname = get_option(options, "dirname")
        if fields_value:
            fields = [f.strip() for f in str(fields_value).split(",") if f.strip()]
            writer = PartitionedWriter(
                dirname or ".",
                fields,
                format_out,
                hive=bool(options.get("hive")),
                max_open_files=int(get_option(options, "max_open_files") or DEFAULT_MAX_OPEN_FILES),
            )
            writer.extension = extension
            count = writer.write_all(rows)
            logger.debug("split: %d records into %d files", count, len(writer.files))
            return
        if options.get("hive"):
            raise ValidationError("--hive needs --fields (the partition fields)", field="hive")
        chunksize = int(get_option(options, "chunksize") or 10000)
        if chunksize < 1:
            raise ValidationError("--chunksize must be at least 1", field="chunksize")
        prefix = get_option(options, "output") or fromfile
        stem = os.path.basename(prefix).split(".", 1)[0] or "part"
        directory = dirname or os.path.dirname(prefix) or "."
        os.makedirs(directory, exist_ok=True)
        count = 0
        for number in itertools.count(1):
            chunk = list(itertools.islice(rows, chunksize))
            if not chunk:
                break
            path = os.path.join(directory, f"{stem}_{number}.{extension}")
            write_rows(iter(chunk), path, format_out=format_out)
            count += len(chunk)
        logger.debug("split: %d records processed", count)
