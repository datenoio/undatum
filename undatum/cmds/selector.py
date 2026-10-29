"""Data selection and filtering module."""

import itertools
import logging
import os
from collections.abc import Iterator
from typing import Any

from ..common.command_utils import (
    ITERABLE_OPTIONS_KEYS,  # noqa: F401
    duckdb_read_expr,
    force_iterable_if_table,
    get_iterable_options,
    iter_command_rows,
    quote_sql_identifier,
)
from ..common.duckdb_config import (
    WORKLOAD_DEFAULTS,
    create_duckdb_connection,
    get_duckdb_config_from_options,
)
from ..common.engine_selector import detect_engine, engine_for_arrow
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
    emit_records,
    resolve_output_format,
)
from ..io import RowSource
from ..ops import write_rows
from ..utils import (
    dict_generator,
    field_values,
    get_option,
)

logger = logging.getLogger(__name__)

LINEEND = b"\n"
# Rows per fetch from aggregate DuckDB results (uniq, frequency).
STREAM_BATCH_ROWS = 10_000


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


def _engine_for_filter(detected_engine: str, filter_expr, command: str):
    """Keep DuckDB when the filter translates to SQL; otherwise fall back to iterable."""
    filter_sql = None
    if detected_engine == "duckdb" and filter_expr:
        filter_sql = translate_filter_to_sql(filter_expr)
        if filter_sql is None:
            logger.info("%s: filter not translatable to SQL, falling back to iterable", command)
            return "iterable", None
    return detected_engine, filter_sql


def _value_text(value: Any) -> str | None:
    """A field value as uniq and frequency compare it: text, ``None`` for a missing value.

    ``None`` is written as an empty CSV field or JSON null, as the DuckDB engine writes it.
    """
    return None if value is None else str(value)


def get_iterable_fields_uniq(iterable, fields, dolog=False, dq_instance=None, filter_expr=None):  # pylint: disable=unused-argument
    """Returns all uniq values of the fields of iterable dictionary."""
    # dq_instance parameter kept for backward compatibility (no longer used)
    n = 0
    uniqval = []
    seen: set[tuple[str | None, ...]] = set()  # uniqval keeps the first-seen order
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
                k = [_value_text(values[n1]) for values in allvals]
                key = tuple(k)
                if key not in seen:
                    seen.add(key)
                    uniqval.append(k)
        except KeyError:
            pass
    return uniqval


def _duckdb_input(conn: Any, filename, filetype, iterableargs, source=None, columns=None) -> str:
    """The DuckDB ``FROM`` expression of the input; ``conn`` is closed when there is none.

    With a ``RowSource``, inputs DuckDB reads through Arrow (ORC, Arrow/Feather) are
    registered on ``conn``, reading only ``columns`` when given.

    Raises:
        ValueError: For inputs DuckDB does not read.
    """
    try:
        if source is None:
            return duckdb_read_expr(filename, filetype, iterableargs, all_varchar=True)
        relation = source.duckdb_relation(conn, columns)
        if relation is None:
            raise ValueError(f"DuckDB cannot read {filename}")
        return relation
    except BaseException:
        conn.close()
        raise


def _first_seen_groups(
    read_expr: str, fieldstext: str, filter_sql: str | None, *, counts: bool
) -> str:
    """Query of the distinct ``fieldstext`` values in the order the Python engine gives.

    Distinct values come in first-seen order; with ``counts`` each ends with its count
    (``c``), most frequent first and ties in first-seen order. ``row_number() OVER ()``
    numbers the records in input order.
    """
    numbered = f"SELECT {fieldstext}, row_number() OVER () AS __undatum_row FROM {read_expr}"
    if filter_sql:
        numbered = f"{numbered} WHERE {filter_sql}"
    if counts:
        return (
            f"SELECT {fieldstext}, count(*) AS c FROM ({numbered}) GROUP BY {fieldstext} "
            "ORDER BY c DESC, min(__undatum_row)"
        )
    return (
        f"SELECT {fieldstext} FROM ({numbered}) GROUP BY {fieldstext} ORDER BY min(__undatum_row)"
    )


def _ordered_connection(duckdb_config: dict[str, Any] | None) -> Any:
    """A connection for queries that number the input (``--duckdb-*`` options win)."""
    return create_duckdb_connection(**{**WORKLOAD_DEFAULTS["ordered"], **(duckdb_config or {})})


def _stream_query(conn: Any, query: str) -> Iterator[tuple[Any, ...]]:
    """Run ``query`` on ``conn`` and fetch its rows in batches; ``conn`` is closed after them.

    The first batch is fetched here, so a query that fails raises before any row is written.
    """
    try:
        result = conn.execute(query)
        first = result.fetchmany(STREAM_BATCH_ROWS)
    except BaseException:
        conn.close()
        raise

    def rows() -> Iterator[tuple[Any, ...]]:
        try:
            batch = first
            while batch:
                yield from batch
                batch = result.fetchmany(STREAM_BATCH_ROWS)
        finally:
            conn.close()

    return rows()


def get_duckdb_fields_uniq(
    filename,
    fields,
    filetype=None,
    duckdb_config=None,
    dolog=False,
    dq_instance=None,
    filter_sql=None,
    iterableargs=None,
    source=None,
):  # pylint: disable=unused-argument
    """Distinct values of ``fields`` in ``filename`` from DuckDB, as an iterator of tuples.

    Values come in first-seen order, as from the Python engine. The query runs before this
    returns, so read errors raise here; rows are then fetched in batches while they are
    written.
    """
    # dq_instance parameter kept for backward compatibility (no longer used)
    conn = _ordered_connection(duckdb_config)
    # Without a filter the query reads only the fields (nested paths need whole columns).
    columns = None if filter_sql or _has_nested_fields(fields) else list(fields)
    read_expr = _duckdb_input(conn, filename, filetype, iterableargs, source, columns)

    fieldstext = ",".join(quote_sql_identifier(field) for field in fields)
    query = _first_seen_groups(read_expr, fieldstext, filter_sql, counts=False)
    if dolog:
        logger.info(query)

    return _stream_query(conn, query)


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
            items.append([*k, v])
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
                kx = tuple(_value_text(values[n1]) for values in allvals)
                valuedict[kx] = valuedict.get(kx, 0) + 1
        except KeyError:
            pass
    for k, v in valuedict.items():
        items.append([*k, v])
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
    iterableargs=None,
    source=None,
):  # pylint: disable=unused-argument
    """``fields`` values and their counts, most frequent first, as an iterator of tuples.

    Ties come in first-seen order, as from the Python engine. The query runs before this
    returns, so read errors raise here; rows are then fetched in batches while they are
    written.
    """
    # dq_instance parameter kept for backward compatibility (no longer used)
    conn = _ordered_connection(duckdb_config)
    # Without a filter the query reads only the fields (nested paths need whole columns).
    columns = None if filter_sql or _has_nested_fields(fields) else list(fields)
    read_expr = _duckdb_input(conn, filename, filetype, iterableargs, source, columns)

    fieldstext = ",".join(quote_sql_identifier(field) for field in fields)
    query = _first_seen_groups(read_expr, fieldstext, filter_sql, counts=True)
    if dolog:
        logger.info(query)

    return _stream_query(conn, query)


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
        source = RowSource(fromfile, options)
        detected_engine = detect_engine(fromfile, engine, filetype, operation="uniq")
        detected_engine = force_iterable_if_table(options, detected_engine)
        detected_engine = engine_for_arrow(detected_engine, engine, source)
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
                    iterableargs=iterableargs,
                    source=source,
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
        written = emit_records(
            _rows_as_dicts(uniqval, fields),
            to_file,
            fieldnames=fields,
            format_out=format_out or None,
            stdout_format=format_out or "csv",
        )
        logger.debug("uniq: %d unique values found", written)

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
        source = RowSource(fromfile, options)
        detected_engine = detect_engine(fromfile, engine, filetype, operation="frequency")
        detected_engine = force_iterable_if_table(options, detected_engine)
        detected_engine = engine_for_arrow(detected_engine, engine, source)
        detected_engine, filter_sql = _engine_for_filter(detected_engine, filter_expr, "frequency")
        items = None
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
                    iterableargs=iterableargs,
                    source=source,
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
        elif items is None:
            raise ValidationError(
                f"Unsupported engine '{detected_engine}'",
                field="engine",
                suggestions=["auto", "duckdb", "python"],
            )
        fields.append("count")
        written = emit_records(
            _rows_as_dicts(items, fields),
            to_file,
            fieldnames=fields,
            format_out=format_out or None,
            stdout_format=format_out or "csv",
        )
        logger.debug("frequency: %d unique values found", written)

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

        to_file = get_option(options, "output")
        format_out = get_option(options, "format_out")
        engine = get_option(options, "engine")
        fields_value = get_option(options, "fields")
        from ..io import open_source
        from ..ops import SelectConfig, run_steps
        from ..ops.expr import where_steps

        steps = where_steps(options)
        fields = [f.strip() for f in (fields_value or "").split(",") if f.strip()]
        if not steps:
            if not fields_value:
                raise ValidationError(
                    "select requires --fields, --where or --add (fields: comma-separated names)",
                    field="fields",
                )
            if not fields:
                raise ValidationError(
                    "select requires at least one field name in 'fields'", field="fields"
                )
        if to_file:
            resolve_output_format(to_file, format_out or None)
        cfg = SelectConfig(fields=tuple(fields), filter=get_option(options, "filter"))
        if cfg.fields or cfg.filter:
            steps = [*steps, ("select", cfg)]
        # One implementation for both engines: the select operation (DuckDB when the input
        # and the fields allow, else Python).
        run_steps(
            steps,
            open_source(fromfile, options),
            to_file,
            engine=engine or "auto",
            format_out=format_out,
            fieldnames=fields or None,
        )

    def split(self, fromfile, options=None):
        """Split a file into chunks of ``chunksize`` records, or into one file per value.

        With ``fields`` every distinct value combination gets its own file
        (``<dirname>/<value>.<ext>``) or, with ``hive``, its own directory
        (``<dirname>/<field>=<value>/data_0.<ext>``). Output files use ``format_out`` or the
        input's format; at most ``max_open_files`` are open at once.
        """
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
