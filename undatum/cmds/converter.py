"""File format conversion module."""

import logging
import time
from collections import defaultdict
from typing import Any

from ..common.chunked_io import chunked_reader
from ..common.command_utils import (
    apply_iterable_csv_delimiter,
    apply_table_selection,
    get_iterable_options,
    parse_column_list,
    parse_row_range,
    resolve_csv_delimiter,
    validate_codec_profile,
    validate_write_mode,
)
from ..common.engine_selector import detect_engine, is_format_supported_by_duckdb
from ..common.errors import (
    FileNotFoundError,
    FormatError,
    PermissionError,
    ValidationError,
    find_similar_files,
)
from ..common.parallel import parallel_process_chunks
from ..common.parallel_workers import transform_convert_chunk
from ..common.path_utils import validate_file_path
from ..common.progress import is_tty, wrap_iterable
from ..constants import COMPRESSED_FILE_TYPES, DUCKABLE_FILE_TYPES, SUPPORTED_FILE_TYPES
from ..utils import get_file_type, get_option

logger = logging.getLogger(__name__)

# Preferred order for suggesting writable conversion targets. The list is
# filtered against iterabledata's actual write capabilities at runtime so the
# suggestions can never contradict the read-only check below.
_PREFERRED_WRITABLE_FORMATS = ["csv", "jsonl", "json", "parquet", "orc", "avro", "bson"]


def _writable_format_suggestions() -> list[str]:
    """Return the preferred writable formats that iterabledata can actually write.

    Falls back to the full preferred list if capability reporting is unavailable.
    """
    try:
        from iterable.helpers.capabilities import supports_write
    except Exception:  # noqa: BLE001 - capabilities unavailable: use static list
        return list(_PREFERRED_WRITABLE_FORMATS)
    writable = []
    for fmt in _PREFERRED_WRITABLE_FORMATS:
        try:
            if supports_write(fmt) is not False:
                writable.append(fmt)
        except Exception:  # noqa: BLE001 - unknown format: skip it
            continue
    return writable or list(_PREFERRED_WRITABLE_FORMATS)


# Formats commonly suggested as writable conversion targets (capability-filtered).
WRITABLE_FORMAT_SUGGESTIONS = _writable_format_suggestions()

# Formats that report as writable but require an externally-supplied schema or
# message class to serialize (e.g. a compiled protobuf message). They cannot be
# used as generic conversion targets, so we fail fast with an actionable error
# instead of surfacing the engine's "requires '<x>' parameter" error. Keys are
# resolved output format ids/extensions; values name the required input.
_SCHEMA_REQUIRED_FORMATS: dict[str, str] = {
    "pb": "a compiled protobuf message class (message_class)",
    "protobuf": "a compiled protobuf message class (message_class)",
    "capnp": "a Cap'n Proto schema (schema_file and schema_name)",
    "thrift": "a generated Thrift struct class (struct_class)",
}


def _native_bulk_pair(format_in: str | None, format_out: str | None) -> bool:
    """Return True when both formats advertise native bulk read/write."""
    if not format_in or not format_out:
        return False
    try:
        from iterable.helpers.capabilities import get_format_capabilities
    except Exception:  # noqa: BLE001
        return False
    try:
        cin = get_format_capabilities(str(format_in).lower()) or {}
        cout = get_format_capabilities(str(format_out).lower()) or {}
    except Exception:  # noqa: BLE001
        return False
    return bool(cin.get("native_bulk_read") and cout.get("native_bulk_write"))


def _skip_duckdb_convert(options: dict) -> bool:
    """DuckDB COPY cannot honor table/sheet, column selection, codec profiles, compression level, CSV quotechar, or Parquet row-group size."""
    if options.get("table") or options.get("sheet"):
        return True
    if options.get("columns") or options.get("row_range"):
        return True
    if options.get("native_batch") is True:
        return True
    if options.get("profile"):
        return True
    if options.get("level") is not None:
        return True
    if options.get("write_mode"):
        return True
    if options.get("row_group_size") is not None:
        return True
    on_error = options.get("on_error")
    if on_error and str(on_error).strip().lower() in ("skip", "warn"):
        return True
    if options.get("error_log"):
        return True
    if options.get("quotechar"):
        return True
    return False


def _filter_bulk_convert_kwargs(bulk_convert_fn, convert_kwargs: dict) -> dict:
    """Drop convert-only kwargs that the installed iterabledata bulk_convert rejects.

    ``iterable.convert.convert`` accepts ``use_native_batch`` / ``selection`` /
    ``strict_native``; ``bulk_convert`` in iterabledata 1.0.21 does not. Filter
    by signature so newer engines pick the flags up automatically.
    """
    import inspect

    params = inspect.signature(bulk_convert_fn).parameters
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return convert_kwargs
    return {key: value for key, value in convert_kwargs.items() if key in params}


DEFAULT_BATCH_SIZE = 50000
LOW_MEMORY_BATCH_SIZE = 5000
DEFAULT_HEADERS_DETECT_LIMIT = 1000

_DEPRECATED_CONVERT_OPTIONS: dict[str, Any] = {
    "skip_end_rows": 0,
    "fields": None,
    "zipfile": False,
}


def df_to_pyorc_schema(df):
    """Build a pyorc schema from the column types of a pandas dataframe."""
    struct_schema = []
    for k, v in df.dtypes.to_dict().items():
        v = str(v)
        if v == "float64":
            struct_schema.append(f"{k}:float")
        elif v == "float32":
            struct_schema.append(f"{k}:float")
        elif v.startswith("datetime64"):
            struct_schema.append(f"{k}:timestamp")
        elif v == "int32":
            struct_schema.append(f"{k}:int")
        elif v == "int64":
            struct_schema.append(f"{k}:int")
        else:
            struct_schema.append(f"{k}:string")
    return struct_schema


def etree_to_dict(t, prefix_strip=True):
    """Convert XML element tree to dictionary."""
    tag = t.tag if not prefix_strip else t.tag.rsplit("}", 1)[-1]
    d = {tag: {} if t.attrib else None}
    children = list(t)
    if children:
        dd = defaultdict(list)
        for dc in map(etree_to_dict, children):
            for k, v in dc.items():
                if prefix_strip:
                    # Remove XML namespace prefix (e.g., '{http://...}tagname' -> 'tagname')
                    k = k.rsplit("}", 1)[-1]
                dd[k].append(v)
        d = {tag: {k: v[0] if len(v) == 1 else v for k, v in dd.items()}}
    if t.attrib:
        d[tag].update(("@" + k.rsplit("}", 1)[-1], v) for k, v in t.attrib.items())
    if t.text:
        text = t.text.strip()
        if children or t.attrib:
            tag = tag.rsplit("}", 1)[-1]
            if text:
                d[tag]["#text"] = text
        else:
            d[tag] = text
    return d


def _is_flat(item):
    """Check if dictionary item is flat (no nested structures)."""
    for _k, v in item.items():
        if isinstance(v, (dict, tuple, list)):
            return False
    return True


def express_analyze_jsonl(filename, itemlimit=100):
    """Quickly analyze JSONL file structure."""
    import orjson

    isflat = True
    n = 0
    keys = set()
    with open(filename, encoding="utf8") as f:
        for line in f:
            n += 1
            if n > itemlimit:
                break
            record = orjson.loads(line)
            if isflat:
                if not _is_flat(record):
                    isflat = False
            if len(keys) == 0:
                keys = set(record.keys())
            else:
                keys = keys.union(set(record.keys()))
    keys = list(keys)
    keys.sort()
    return {"isflat": isflat, "keys": keys}


def make_flat(item):
    """Flatten nested structures in dictionary by converting to strings."""
    result = {}
    for k, v in item.items():
        if isinstance(v, (tuple, list, dict)):
            result[k] = str(v)
        else:
            result[k] = v
    return result


def _warn_deprecated_convert_options(options: dict) -> None:
    """Warn when legacy convert flags are set but not supported by the engine."""
    for key, default in _DEPRECATED_CONVERT_OPTIONS.items():
        value = options.get(key)
        if value not in (None, default):
            logger.warning(
                "Option '%s' is deprecated for convert and has no effect with the "
                "iterabledata engine",
                key,
            )


def _format_bytes(num_bytes: int | None) -> str:
    if num_bytes is None:
        return ""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


def format_conversion_summary(result) -> str:
    """Format a one-line summary from iterabledata's ConversionResult."""
    parts = [f"Converted {result.rows_out:,} rows in {result.elapsed_seconds:.1f}s"]
    if result.bytes_written:
        parts.append(f"({_format_bytes(result.bytes_written)} written)")
    if result.errors:
        parts.append(f"({len(result.errors)} errors)")
    return " ".join(parts)


def format_bulk_conversion_summary(result) -> str:
    """Format a one-line summary from iterabledata's BulkConversionResult."""
    parts = [
        f"Bulk converted {result.successful_files}/{result.total_files} files",
        f"({result.total_rows_out:,} rows in {result.total_elapsed_seconds:.1f}s)",
    ]
    if result.failed_files:
        parts.append(f"({result.failed_files} failed)")
    return " ".join(parts)


class Converter:
    """File format converter handler."""

    def __init__(self, batch_size=DEFAULT_BATCH_SIZE):
        self.batch_size = batch_size

    @staticmethod
    def _resolve_output_format(tofile, options: dict) -> str | None:
        """Determine the output data format id from the target path or options.

        Strips a trailing compression-codec extension (e.g. ``.gz``) so that
        ``out.csv.gz`` resolves to ``csv``.
        """
        fmt = options.get("format_out")
        if fmt:
            return fmt.lower()
        basename = str(tofile).rsplit("/", 1)[-1]
        parts = basename.split(".")
        if len(parts) >= 2 and parts[-1].lower() in COMPRESSED_FILE_TYPES:
            parts = parts[:-1]
        if len(parts) >= 2:
            return parts[-1].lower()
        return None

    def _check_output_schema_required(self, tofile, options: dict) -> None:
        """Raise a clear error when the output format needs an external schema.

        Some formats (protobuf, Cap'n Proto, Thrift) report as writable but
        cannot serialize plain records without a compiled schema/message class,
        so they are not valid generic conversion targets.
        """
        out_fmt = self._resolve_output_format(tofile, options)
        if not out_fmt:
            return
        requirement = _SCHEMA_REQUIRED_FORMATS.get(out_fmt)
        if requirement is not None:
            raise ValidationError(
                f"Output format '{out_fmt}' requires {requirement} and cannot be used as a "
                f"generic conversion target. Convert to a self-describing format instead.",
                field="output",
                suggestions=[
                    f for f in WRITABLE_FORMAT_SUGGESTIONS if f not in _SCHEMA_REQUIRED_FORMATS
                ],
            )

    def _convert_partitioned(self, fromfile: str, tofile: str, options: dict) -> None:
        """Write ``fromfile`` as a Hive-partitioned directory ``tofile``."""
        from ..common.writer import resolve_output_format
        from ..io import RowSource
        from ..io.partition import (
            DEFAULT_MAX_OPEN_FILES,
            PartitionedWriter,
            check_output_directory,
            duckdb_partitioned_copy,
        )
        from ..ops import compose_sql, get_operation
        from ..ops.expr import where_steps

        fields = [f.strip() for f in str(options["partition_by"]).split(",") if f.strip()]
        max_open = int(get_option(options, "max_open_files") or DEFAULT_MAX_OPEN_FILES)
        if "://" not in fromfile:
            validate_file_path(fromfile, check_read=True)
        check_output_directory(tofile)
        source = RowSource(fromfile, options)
        format_out = (get_option(options, "format_out") or source.format_id or "").lower()
        if not format_out:
            raise ValidationError(
                "--partition-by needs --format-out when the input format is unknown",
                field="format_out",
            )
        resolve_output_format(f"part.{format_out}", format_out)
        steps = [(get_operation(name), cfg) for name, cfg in where_steps(options)]

        relation = None
        if (get_option(options, "engine") or "auto") != "python":
            relation = source.duckdb_from()
        if relation is not None:
            import duckdb

            conn = duckdb.connect()
            try:
                query = compose_sql(conn, relation, steps) if steps else f"SELECT * FROM {relation}"
                if query and duckdb_partitioned_copy(
                    conn, query, tofile, fields, format_out, max_open
                ):
                    logger.debug("convert: partitioned with DuckDB into %s", tofile)
                    return
            except duckdb.Error as exc:
                logger.warning("DuckDB partitioning failed, using the Python engine: %s", exc)
            finally:
                conn.close()

        rows: Any = source
        for op, cfg in steps:
            rows = op.apply(rows, cfg)
        writer = PartitionedWriter(tofile, fields, format_out, max_open_files=max_open)
        count = writer.write_all(rows)
        logger.debug("convert: %d records into %d partition files", count, len(writer.files))

    def _check_output_writable(self, tofile, options: dict) -> None:
        """Raise a clear error when the output format is read-only.

        Uses iterabledata's capability reporting so undatum fails fast with an
        actionable message instead of a cryptic engine error.

        Parquet is treated as writable when ``pyarrow`` is importable, even if
        iterabledata's capability probe reports False (common when pyarrow was
        missing at probe time). DuckDB can also write Parquet via COPY.
        """
        out_fmt = self._resolve_output_format(tofile, options)
        if not out_fmt:
            return
        if out_fmt == "parquet":
            try:
                import pyarrow  # noqa: F401

                return
            except ImportError:
                from ..common.errors import DependencyError

                raise DependencyError(
                    "pyarrow",
                    feature="Parquet write",
                    install_command="pip install pyarrow",
                ) from None
        try:
            from iterable.helpers.capabilities import supports_write

            writable = supports_write(out_fmt)
        except Exception:  # noqa: BLE001 - unknown format: let the engine decide
            return
        if writable is False:
            raise ValidationError(
                f"Output format '{out_fmt}' is read-only; undatum can read it but cannot "
                f"write to it.",
                field="output",
                suggestions=WRITABLE_FORMAT_SUGGESTIONS,
            )

    def _build_convert_kwargs(
        self, options: dict, limit, fromfile: str | None = None, tofile: str | None = None
    ) -> dict:
        """Translate undatum convert options into iterabledata convert kwargs."""
        iterableargs = apply_table_selection(fromfile, get_iterable_options(options))
        toiterableargs: dict = {}

        format_in = options.get("format_in")
        format_out = options.get("format_out")
        if format_in:
            iterableargs["format"] = str(format_in).lower()
        if format_out:
            toiterableargs["format"] = str(format_out).lower()

        compression = options.get("compression")
        if compression:
            toiterableargs["compression"] = compression

        profile = validate_codec_profile(options.get("profile"))
        write_mode = validate_write_mode(options.get("write_mode"))
        if write_mode:
            toiterableargs["write_mode"] = write_mode
        row_group_size = options.get("row_group_size")
        if row_group_size is not None:
            try:
                row_group_size = int(row_group_size)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    f"row_group_size must be a positive integer, got {row_group_size!r}.",
                    field="row_group_size",
                ) from exc
            if row_group_size < 1:
                raise ValidationError(
                    f"row_group_size must be a positive integer, got {row_group_size!r}.",
                    field="row_group_size",
                )
            toiterableargs["row_group_size"] = row_group_size

        filetype = iterableargs.get("format") or (get_file_type(fromfile) if fromfile else None)
        delimiter = resolve_csv_delimiter(iterableargs, filename=fromfile, filetype=filetype)
        if delimiter:
            # Input dialect only: the output delimiter follows the output format.
            iterableargs["delimiter"] = delimiter
        quotechar = iterableargs.get("quotechar")
        if quotechar:
            toiterableargs["quotechar"] = quotechar

        is_flatten = bool(get_option(options, "flatten"))
        show_progress = get_option(options, "progress")
        if show_progress is None:
            show_progress = True
        # Progress goes to stderr and only makes sense in a terminal.
        show_progress = bool(show_progress) and is_tty()

        scan_limit = options.get("scan_limit")
        if scan_limit is None:
            scan_limit = limit if limit is not None else DEFAULT_HEADERS_DETECT_LIMIT
        batch_size = options.get("batch_size", self.batch_size)
        if options.get("low_memory") and (
            options.get("batch_size") is None or batch_size == self.batch_size == DEFAULT_BATCH_SIZE
        ):
            # Prefer smaller batches unless the user explicitly set batch_size.
            if options.get("batch_size") is None:
                batch_size = LOW_MEMORY_BATCH_SIZE

        columns = parse_column_list(options.get("columns"))
        row_range = parse_row_range(options.get("row_range"))
        table_name = iterableargs.get("table")
        selection = None
        if columns or row_range or table_name:
            selection = {}
            if columns:
                selection["columns"] = columns
            if row_range:
                selection["row_range"] = row_range
            if table_name:
                selection["table"] = table_name

        use_native_batch = self._resolve_native_batch(
            options, fromfile, tofile, selection is not None
        )
        if use_native_batch and batch_size:
            selection = dict(selection or {})
            selection["batch_size"] = int(batch_size)

        kwargs = {
            "iterableargs": iterableargs,
            "toiterableargs": toiterableargs,
            "scan_limit": scan_limit,
            "batch_size": batch_size,
            "is_flatten": is_flatten,
            "silent": not show_progress,
            "show_progress": show_progress,
            "atomic": bool(options.get("atomic", False)),
            "use_native_batch": use_native_batch,
            "strict_native": bool(options.get("strict_native", False)),
            "use_totals": bool(options.get("use_totals", False)),
        }
        if selection:
            kwargs["selection"] = selection
        codecargs: dict = {}
        if profile:
            codecargs["profile"] = profile
        level = options.get("level")
        if level is not None:
            codecargs["compression_level"] = int(level)
        if codecargs:
            kwargs["codecargs"] = codecargs
        return kwargs

    @staticmethod
    def _resolve_native_batch(
        options: dict,
        fromfile: str | None,
        tofile: str | None,
        has_selection: bool,
    ) -> bool:
        """Decide whether to request iterabledata's native batch convert path."""
        explicit = options.get("native_batch")
        if explicit is True:
            return True
        if explicit is False:
            return False
        if has_selection:
            return True
        if not options.get("low_memory"):
            return False
        in_fmt = options.get("format_in") or (get_file_type(fromfile) if fromfile else None)
        out_fmt = options.get("format_out") or (
            Converter._resolve_output_format(tofile, options) if tofile else None
        )
        return _native_bulk_pair(in_fmt, out_fmt)

    @staticmethod
    def _with_codecargs(codecargs: dict | None):
        """Inject codecargs into iterable.convert's writer open_iterable calls."""
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            if not codecargs:
                yield
                return
            import iterable.convert.core as convert_core

            original = convert_core.open_iterable

            def wrapped(*args, **kwargs):
                mode = kwargs.get("mode")
                if mode is None and len(args) >= 2:
                    mode = args[1]
                if mode in ("w", "wb"):
                    kwargs = dict(kwargs)
                    merged = dict(kwargs.get("codecargs") or {})
                    merged.update(codecargs)
                    kwargs["codecargs"] = merged
                return original(*args, **kwargs)

            convert_core.open_iterable = wrapped
            try:
                yield
            finally:
                convert_core.open_iterable = original

        return _ctx()

    @staticmethod
    def _with_csv_options(iterableargs: dict | None, toiterableargs: dict | None = None):
        """Apply CSV delimiter/quotechar after iterable.convert opens a file.

        ``open_iterable`` passes those keys via ``options=``; CSVIterable only
        reads constructor kwargs.
        """
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            import iterable.convert.core as convert_core

            original = convert_core.open_iterable

            def wrapped(*args, **kwargs):
                iterable = original(*args, **kwargs)
                mode = kwargs.get("mode")
                if mode is None and len(args) >= 2:
                    mode = args[1]
                filename = args[0] if args else kwargs.get("filename")
                csv_args = toiterableargs if mode in ("w", "wb") else iterableargs
                apply_iterable_csv_delimiter(iterable, filename, csv_args)
                return iterable

            convert_core.open_iterable = wrapped
            try:
                yield
            finally:
                convert_core.open_iterable = original

        return _ctx()

    def _try_duckdb_convert(self, fromfile, tofile, options: dict) -> bool:
        """Attempt DuckDB spill-to-disk conversion for duckable → Parquet/CSV/JSONL.

        Returns:
            True if conversion completed via DuckDB, False if caller should fall back.
        """
        out_fmt = self._resolve_output_format(tofile, options)
        if out_fmt not in ("parquet", "csv", "json", "jsonl"):
            return False

        engine = get_option(options, "engine") or "auto"
        low_memory = bool(options.get("low_memory"))
        # Prefer DuckDB for low-memory parquet/csv/jsonl or when engine requests it.
        if engine == "python":
            return False
        if engine == "auto" and not low_memory and out_fmt != "parquet":
            # Keep existing iterable path as default for non-parquet unless low-memory.
            return False

        detected = detect_engine(
            fromfile, engine if engine != "auto" else "auto", operation="convert"
        )
        if detected != "duckdb" and not (low_memory and engine == "auto"):
            # Still try duckdb if format looks duckable under low-memory.
            ftype = get_file_type(fromfile)
            if not is_format_supported_by_duckdb(ftype, "raw") and ftype not in DUCKABLE_FILE_TYPES:
                return False

        try:
            from iterable.helpers.detect import detect_file_type

            from ..common.duckdb_config import (
                create_duckdb_connection,
                get_duckdb_config_from_options,
            )

            ftype_info = detect_file_type(fromfile)
            filetype = options.get("format_in")
            compression = "raw"
            if not filetype and ftype_info.get("success"):
                filetype = ftype_info["datatype"].id()
                if ftype_info.get("codec") is not None:
                    compression = ftype_info["codec"].id()
            filetype = (filetype or get_file_type(fromfile) or "").lower()
            if not is_format_supported_by_duckdb(filetype, compression):
                return False

            if filetype == "csv":
                read_expr = f"read_csv_auto('{fromfile}', all_varchar=true)"
            elif filetype in ("json", "jsonl"):
                read_expr = f"read_json_auto('{fromfile}')"
            elif filetype == "parquet":
                read_expr = f"read_parquet('{fromfile}')"
            else:
                return False

            duckdb_config = get_duckdb_config_from_options(options)
            if low_memory and not duckdb_config.get("memory"):
                duckdb_config["memory"] = "1GB"
            conn = create_duckdb_connection(**duckdb_config)
            try:
                query = f"SELECT * FROM {read_expr}"
                if out_fmt == "parquet":
                    conn.execute(f"COPY ({query}) TO '{tofile}' (FORMAT PARQUET)")
                elif out_fmt == "csv":
                    conn.execute(f"COPY ({query}) TO '{tofile}' (FORMAT CSV, HEADER)")
                else:
                    conn.execute(f"COPY ({query}) TO '{tofile}' (FORMAT JSON)")
            finally:
                conn.close()
            logger.info("convert: completed via DuckDB spill path (%s → %s)", filetype, out_fmt)
            return True
        except Exception as exc:  # noqa: BLE001 - fall back to iterable path
            logger.warning("DuckDB convert path failed, falling back to iterable: %s", exc)
            return False

    def convert(self, fromfile, tofile, options=None, limit=DEFAULT_HEADERS_DETECT_LIMIT):
        """Convert a file (or cloud/DB source) to another format.

        Delegates to iterabledata's ``iterable.convert.convert``, which performs
        schema scanning, batched streaming writes, optional flattening, progress
        reporting, atomic local writes, and native cloud (s3/gs/az) handling.
        Friendly errors for missing files and unsupported formats are preserved.

        When ``low_memory`` is set (or converting duckable formats to Parquet),
        prefers DuckDB ``COPY`` spill-to-disk when possible.

        Args:
            fromfile: Path or URI of the input source.
            tofile: Path or URI of the output file.
            options: Dictionary of conversion options (encoding, delimiter, etc.).
            limit: Maximum records to sample for schema detection.

        Returns:
            iterabledata ``ConversionResult`` with row/byte metrics, or ``None``
            when DuckDB completed the conversion.

        Raises:
            FileNotFoundError: If a local input file does not exist.
            PermissionError: If a local file cannot be read.
            FormatError: If the input format is not supported.
        """
        if options is None:
            options = {}

        _warn_deprecated_convert_options(options)

        if get_option(options, "partition_by"):
            return self._convert_partitioned(fromfile, tofile, options)

        # Fail fast with an actionable message if the output format is read-only
        # or requires an external schema (protobuf/capnp/thrift).
        self._check_output_writable(tofile, options)
        self._check_output_schema_required(tofile, options)

        # Validate local input files; cloud/DB URIs are validated by the engine.
        if "://" not in fromfile:
            try:
                validate_file_path(fromfile, check_read=True)
            except FileNotFoundError as e:
                suggestions = find_similar_files(fromfile)
                raise FileNotFoundError(fromfile, suggestions) from e
            except PermissionError as e:
                raise PermissionError(fromfile, operation="read") from e

        from ..ops.expr import where_steps

        steps = where_steps(options)
        if steps:
            # --where / --add: one DuckDB query (or batched expressions) into any format.
            from ..io import RowSource
            from ..ops import run_steps

            run_steps(
                steps,
                RowSource(fromfile, options),
                tofile,
                engine=get_option(options, "engine") or "auto",
                format_out=get_option(options, "format_out"),
            )
            return None

        if "://" not in fromfile and not _skip_duckdb_convert(options):
            if self._try_duckdb_convert(fromfile, tofile, options):
                return None

        convert_kwargs = self._build_convert_kwargs(
            options, limit, fromfile=fromfile, tofile=tofile
        )
        codecargs = convert_kwargs.pop("codecargs", None)
        threads = get_option(options, "threads")
        # Process-pool path for single-file Python/iterable engine only.
        # Skip cloud/DB URIs and DuckDB (already handled above).
        if (
            threads
            and int(threads) > 1
            and "://" not in fromfile
            and "://" not in str(tofile)
            and (get_option(options, "engine") or "auto") != "duckdb"
            and not convert_kwargs.get("use_native_batch")
        ):
            try:
                result = self._convert_python_parallel(
                    fromfile, tofile, convert_kwargs, int(threads), options, codecargs=codecargs
                )
                if options.get("summary", True):
                    logger.info(format_conversion_summary(result))
                return result
            except Exception as e:
                logger.warning(
                    "Parallel convert failed (%s); falling back to sequential iterable path",
                    e,
                )

        from iterable.convert import convert as iterable_convert

        try:
            with self._with_codecargs(codecargs):
                with self._with_csv_options(
                    convert_kwargs.get("iterableargs"),
                    convert_kwargs.get("toiterableargs"),
                ):
                    result = iterable_convert(fromfile, tofile, **convert_kwargs)
        except (FileNotFoundError, PermissionError, FormatError):
            raise
        except Exception as e:
            # Surface a helpful error when the input format is not supported.
            file_type = get_file_type(fromfile)
            if file_type is None or file_type not in SUPPORTED_FILE_TYPES:
                raise FormatError(fromfile, file_type, SUPPORTED_FILE_TYPES) from e
            # Actionable hint when Parquet support is missing
            if "pyarrow" in str(e).lower() or "parquet" in str(e).lower():
                try:
                    import pyarrow  # noqa: F401
                except ImportError as import_err:
                    from ..common.errors import DependencyError

                    raise DependencyError(
                        "pyarrow",
                        feature="Parquet read/write",
                        install_command="pip install pyarrow",
                    ) from import_err
            raise

        if options.get("summary", True):
            logger.info(format_conversion_summary(result))
        return result

    def _convert_python_parallel(
        self,
        fromfile: str,
        tofile: str,
        convert_kwargs: dict,
        threads: int,
        options: dict,
        codecargs: dict | None = None,
    ):
        """Convert via process-pool chunk transforms with ordered writes.

        Reads and writes stay on the main process; CPU-bound flatten/pad work
        runs in worker processes. Record order is preserved.
        """
        import os

        from iterable.helpers.detect import is_flat
        from iterable.helpers.utils import dict_generator, make_flat
        from iterable.types import ConversionResult

        from ..common.s3_iterable import open_path as open_iterable

        start = time.time()
        iterableargs = dict(convert_kwargs.get("iterableargs") or {})
        toiterableargs = dict(convert_kwargs.get("toiterableargs") or {})
        scan_limit = convert_kwargs.get("scan_limit")
        batch_size = int(convert_kwargs.get("batch_size") or self.batch_size)
        is_flatten = bool(convert_kwargs.get("is_flatten"))
        show_progress = bool(convert_kwargs.get("show_progress", True))
        atomic = bool(convert_kwargs.get("atomic", False))
        silent = bool(convert_kwargs.get("silent", False))

        # Smaller in-flight window under low-memory mode.
        window_factor = 1 if options.get("low_memory") else 2
        max_in_flight = max(threads * window_factor, threads)

        source_engine = iterableargs.pop("engine", "internal")

        def reopen_source():
            return open_iterable(
                fromfile, mode="r", engine=source_engine, iterableargs=iterableargs
            )

        actual_tofile = tofile
        temp_file: str | None = None
        if atomic:
            temp_file = os.path.join(
                os.path.dirname(tofile) or ".", os.path.basename(tofile) + ".tmp"
            )
            if os.path.exists(temp_file):
                os.remove(temp_file)
            actual_tofile = temp_file

        it_in = reopen_source()
        it_out = None
        rows_in = 0
        rows_out = 0
        try:
            keys: list[str] = []
            is_flat_output = is_flat(tofile)
            if is_flat_output:
                key_set: set[str] = set()
                n = 0
                for item in it_in:
                    if scan_limit is not None and n >= scan_limit:
                        break
                    n += 1
                    if is_flatten:
                        key_set.update(make_flat(item).keys())
                    else:
                        for path in dict_generator(item):
                            key_set.add(".".join(path[:-1]))
                keys = sorted(key_set)
                try:
                    it_in.reset()
                except NotImplementedError:
                    it_in.close()
                    it_in = reopen_source()

            out_args: dict[str, Any] = dict(toiterableargs)
            if is_flat_output:
                out_args = {"keys": keys, **out_args}
            if actual_tofile != tofile and "format" not in out_args:
                out_ext = tofile.lower().rsplit(".", 1)[-1] if "." in tofile else ""
                if out_ext:
                    out_args["format"] = out_ext

            it_out = open_iterable(
                actual_tofile, mode="w", iterableargs=out_args, codecargs=codecargs
            )

            records = wrap_iterable(
                it_in,
                desc="Converting",
                unit="rows",
                show_progress=show_progress and not silent,
            )
            chunks = chunked_reader(records, chunk_size=batch_size)

            def _payload_chunks():
                for chunk in chunks:
                    yield (list(chunk), keys, is_flatten)

            for processed in parallel_process_chunks(
                transform_convert_chunk,
                _payload_chunks(),
                num_threads=threads,
                use_processes=True,
                preserve_order=True,
                max_in_flight=max_in_flight,
            ):
                if not processed:
                    continue
                it_out.write_bulk(processed)
                rows_in += len(processed)
                rows_out += len(processed)

            if atomic and temp_file:
                os.replace(temp_file, tofile)
                temp_file = None
        finally:
            if it_out is not None:
                try:
                    it_out.close()
                except Exception:  # noqa: BLE001
                    pass
            try:
                it_in.close()
            except Exception:  # noqa: BLE001
                pass
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except OSError:
                    pass

        logger.info(
            "convert: completed via parallel Python path (%d workers, %d rows)",
            threads,
            rows_out,
        )
        return ConversionResult(
            rows_in=rows_in,
            rows_out=rows_out,
            elapsed_seconds=time.time() - start,
        )

    def bulk_convert(self, source, dest, options=None, to_ext=None, parallel=None):
        """Convert many files (directory or glob) via iterabledata's bulk_convert.

        Args:
            source: Directory path or glob pattern of input files.
            dest: Output directory.
            options: Conversion options (same as :meth:`convert`). Use
                ``filename_pattern`` for bulk output names with ``{name}``,
                ``{stem}``, and ``{ext}``.
            to_ext: Target extension (e.g. ``"parquet"``); falls back to the
                ``format_out`` option.
            parallel: Force parallel execution; defaults to True when a thread
                count is supplied via options.

        Returns:
            iterabledata ``BulkConversionResult``.

        Raises:
            ValidationError: If no target extension can be determined.
        """
        if options is None:
            options = {}

        _warn_deprecated_convert_options(options)

        target_ext = to_ext or options.get("format_out")
        if not target_ext:
            raise ValidationError(
                "Bulk conversion requires a target extension (use --to-ext or --format-out).",
                field="output",
                suggestions=WRITABLE_FORMAT_SUGGESTIONS,
            )

        # Fail fast if the requested target format is read-only or schema-required.
        self._check_output_writable(f"x.{target_ext}", {})
        self._check_output_schema_required(f"x.{target_ext}", {})

        from iterable.convert import bulk_convert as iterable_bulk_convert

        convert_kwargs = self._build_convert_kwargs(
            options, DEFAULT_HEADERS_DETECT_LIMIT, fromfile=source, tofile=f"x.{target_ext}"
        )
        codecargs = convert_kwargs.pop("codecargs", None)
        convert_kwargs = _filter_bulk_convert_kwargs(iterable_bulk_convert, convert_kwargs)
        threads = get_option(options, "threads")
        use_parallel = parallel if parallel is not None else bool(threads)

        logger.info("Bulk mode: converting %s -> %s (target: .%s)", source, dest, target_ext)
        pattern = options.get("filename_pattern") or None
        with self._with_codecargs(codecargs):
            with self._with_csv_options(
                convert_kwargs.get("iterableargs"),
                convert_kwargs.get("toiterableargs"),
            ):
                result = iterable_bulk_convert(
                    source,
                    dest,
                    to_ext=target_ext,
                    pattern=pattern,
                    parallel=use_parallel,
                    workers=threads if threads else None,
                    **convert_kwargs,
                )
        if options.get("summary", True):
            logger.info(format_bulk_conversion_summary(result))
        return result
