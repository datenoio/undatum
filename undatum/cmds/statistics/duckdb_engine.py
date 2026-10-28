"""DuckDB-backed statistics computations (mixin)."""

import logging
from contextlib import nullcontext

import duckdb
from iterable.helpers.detect import detect_file_type

from ...common.command_utils import (
    duckdb_read_csv_expr,
    get_iterable_options,
    resolve_csv_delimiter,
)
from ...common.duckdb_config import duckdb_connection
from ...common.field_types import column_types
from ...common.progress import progress
from ...common.s3_iterable import open_iterable_with_s3
from ...common.schema_utils import duckdb_decompose
from ...constants import DEFAULT_DICT_SHARE
from ...io import RowSource
from ...utils import dict_generator, get_option
from .engine import stats_type_names

logger = logging.getLogger(__name__)


class DuckDBStatsMixin:
    """DuckDB statistics engine methods for StatProcessor."""

    _duckdb_conn: duckdb.DuckDBPyConnection | None = None

    @property
    def _duckdb(self) -> duckdb.DuckDBPyConnection:
        """Connection of the current stats run (a default one when used on its own)."""
        if self._duckdb_conn is None:
            self._duckdb_conn = duckdb_connection()
        return self._duckdb_conn

    def _describe_duckdb_fields(self, fromfile, filetype, delimiter=None):
        """Field paths of the input and their DuckDB types, without reading every record.

        Args:
            fromfile: Path to input file
            filetype: File type ('csv', 'jsonl', 'json', etc.)
            delimiter: CSV delimiter (auto-detected when omitted)

        Returns:
            list: ``(field_path, duckdb_type)`` pairs; struct members as dotted paths.
        """
        columns = duckdb_decompose(
            filename=fromfile,
            filetype=filetype,
            path="*",
            limit=None,
            recursive=True,
            ignore_errors=False,  # a bad record must not shrink the counts unnoticed
            use_summarize=False,
            delimiter=delimiter,
            conn=self._duckdb,
        )
        fields = []
        for column in columns:
            field_path = column[0] if column else None
            if not field_path or not isinstance(field_path, str) or field_path == "None":
                continue
            if field_path.startswith(".") or field_path[0].isdigit():
                continue
            fields.append((field_path, column[1]))
        return fields

    # Fields whose distinct values are counted, or grouped into dictionaries, in one scan.
    # DuckDB holds every distinct value of a scan's fields, so both bound its memory.
    DISTINCT_VALUES_PER_SCAN = 2_000_000
    DICTIONARY_FIELDS_PER_SCAN = 4

    def _compute_duckdb_profile(
        self, fromfile, filetype, field_paths, numeric_paths, delimiter=None
    ):
        """Per-field counts, missing values, lengths and numeric distributions in one scan.

        Distinct values are estimated (``approx_count_distinct``, as in ``SUMMARIZE``); exact
        counts come from :meth:`_compute_duckdb_dictionaries` and
        :meth:`_compute_duckdb_distinct`.

        Args:
            fromfile: Path to input file
            filetype: File type ('csv', 'jsonl', 'json', etc.)
            field_paths: Field paths to profile
            numeric_paths: Fields that also get min, max, mean, median and stddev
            delimiter: CSV delimiter (auto-detected when omitted)

        Returns:
            tuple: (number of records, {field_path: statistics})
        """
        read_func = self._duckdb_read_func(fromfile, filetype, delimiter)
        columns = ["COUNT(*)"]
        layout = []
        for field_path in field_paths:
            quoted_field = self._quote_field_path(field_path)
            if quoted_field is None:
                continue
            length = f"LENGTH(CAST({quoted_field} AS VARCHAR))"
            exprs = [
                f"COUNT({quoted_field})",
                f"approx_count_distinct({quoted_field})",  # what SUMMARIZE reports
                f"MIN({length})",
                f"MAX({length})",
                f"AVG({length})",
            ]
            if field_path in numeric_paths:
                number = f"TRY_CAST({quoted_field} AS DOUBLE)"
                exprs += [f"{func}({number})" for func in ("MIN", "MAX", "AVG", "MEDIAN", "STDDEV")]
            columns.extend(exprs)
            layout.append((field_path, len(exprs)))
        row = self._duckdb.execute(f"SELECT {', '.join(columns)} FROM {read_func}").fetchall()[0]
        total = int(row[0] or 0)
        profile = {}
        position = 1
        for field_path, width in layout:
            values = row[position : position + width]
            position += width
            present, approx, minlen, maxlen, avglen = values[:5]
            missing = total - int(present or 0)
            stats = {
                "n_uniq": int(approx or 0),
                "total": total,
                "share_uniq": float(f"{(approx or 0) * 100.0 / total:0.2f}") if total else 0.0,
                "minlen": int(minlen) if minlen is not None else None,
                "maxlen": int(maxlen) if maxlen is not None else 0,
                "avglen": float(avglen) if avglen is not None else 0.0,
                "missing_count": missing,
                "missing_rate": round(missing * 100.0 / total, 2) if total else 0.0,
                "cardinality_pct": 0.0,  # set from the exact distinct counts
            }
            if avglen and total:
                stats["totallen"] = int(avglen * total)
            if width > 5 and values[7] is not None:
                for name, value in zip(
                    ("min", "max", "mean", "median", "stddev"), values[5:], strict=True
                ):
                    stats[name] = float(value) if value is not None else None
            profile[field_path] = stats
        return total, profile

    def _compute_duckdb_distinct(self, fromfile, filetype, estimates, delimiter=None):
        """Exact numbers of distinct non-null values, a few fields per scan.

        Args:
            fromfile: Path to input file
            filetype: File type ('csv', 'jsonl', 'json', etc.)
            estimates: Field path -> estimated distinct values; fields are packed into scans
                of at most ``DISTINCT_VALUES_PER_SCAN`` estimated values (one field when it has
                more)
            delimiter: CSV delimiter (auto-detected when omitted)

        Returns:
            dict: Field path -> distinct values
        """
        read_func = self._duckdb_read_func(fromfile, filetype, delimiter)
        batches: list[list[tuple[str, str]]] = []
        size = 0
        for field_path, estimate in sorted(estimates.items(), key=lambda item: item[1]):
            quoted_field = self._quote_field_path(field_path)
            if quoted_field is None:
                continue
            if not batches or size + estimate > self.DISTINCT_VALUES_PER_SCAN:
                batches.append([])
                size = 0
            batches[-1].append((field_path, quoted_field))
            size += estimate
        distinct = {}
        for batch in batches:
            counts = ", ".join(f"COUNT(DISTINCT {quoted})" for _, quoted in batch)
            row = self._duckdb.execute(f"SELECT {counts} FROM {read_func}").fetchall()[0]
            for (field_path, _), count in zip(batch, row, strict=True):
                distinct[field_path] = int(count or 0)
        return distinct

    def _duckdb_field_types(self, fromfile, options, field_paths):
        """Stats type names of the fields, by the shared rules of ``common.field_types``."""
        source = RowSource(fromfile, options)
        relation = source.duckdb_from()
        if relation is None:
            return {}
        codes: set[str] = set()
        types = column_types(
            self._duckdb, relation, text_values=source.format_id in ("csv", "tsv"), codes=codes
        )
        names = stats_type_names(types, codes)
        return {path: names[path] for path in field_paths if path in names}

    @staticmethod
    def _duckdb_read_func(fromfile, filetype, delimiter=None):
        """Build a DuckDB read function expression for the given file."""
        if filetype in ["csv", "tsv"]:
            return duckdb_read_csv_expr(fromfile, delimiter)
        escaped = fromfile.replace("'", "''")
        if filetype in ["json", "jsonl"]:
            return f"read_json('{escaped}')"
        return f"'{escaped}'"

    @staticmethod
    def _quote_field_path(field_path):
        """Quote a (possibly nested) field path for use in a DuckDB query.

        Returns None if the path is invalid.
        """
        if not field_path or not isinstance(field_path, str) or field_path == "None":
            return None
        if field_path.startswith(".") or field_path[0].isdigit():
            return None
        field_parts = field_path.split(".")
        if any(not part or part == "None" for part in field_parts):
            return None
        return ".".join(f'"{part}"' for part in field_parts)

    def _infer_field_types(self, fielddata, finfields, categorical_threshold=10.0):
        """Infer field type categories (categorical vs numerical) from statistics.

        Args:
            fielddata: Dictionary of field statistics
            finfields: Dictionary mapping field paths to final types
            categorical_threshold: Max cardinality percentage for categorical fields

        Returns:
            dict: Mapping from field_path to dict with 'category',
                'is_categorical' and 'is_numerical' keys
        """
        type_inference = {}
        for field_path, fd in fielddata.items():
            base_type = finfields.get(field_path, "str")
            is_numerical = base_type in ("int", "float", "numeric")
            cardinality = fd.get("cardinality_pct", fd.get("share_uniq", 100.0)) or 0.0
            is_categorical = not is_numerical and cardinality <= categorical_threshold
            if is_numerical:
                category = "numerical"
            elif is_categorical:
                category = "categorical"
            else:
                category = "text"
            type_inference[field_path] = {
                "category": category,
                "is_categorical": is_categorical,
                "is_numerical": is_numerical,
            }
        return type_inference

    def _detect_types_from_sample(self, fromfile, filetype, field_paths, show_progress=False):
        """Detect field types by sampling records and using guess_datatype.

        This maintains compatibility with iterable engine's type detection logic.
        Uses iterable engine to sample records (fast for small samples) to preserve
        nested structure handling, while leveraging DuckDB for bulk aggregations.

        Args:
            fromfile: Path to input file
            filetype: File type ('csv', 'jsonl', 'json', etc.)
            field_paths: List of field paths to detect types for
            show_progress: Whether to show progress indication during sampling

        Returns:
            dict: Mapping from field_path to type distribution dictionary
        """
        # Initialize type distributions for each field
        type_distributions = {field_path: {} for field_path in field_paths}

        # Use iterable engine for sampling (handles nested structures correctly)
        # This is fast for small samples (10000 records) and maintains accuracy
        sample_limit = 10000
        iterableargs = {}
        iterable_context = open_iterable_with_s3(fromfile, mode="r", iterableargs=iterableargs)
        iterable = iterable_context.__enter__()

        try:
            count = 0
            # Wrap with progress bar if requested
            iterable_wrapped = iterable
            if show_progress:
                iterable_wrapped = progress(
                    iterable,
                    total=sample_limit,
                    desc="Sampling for type detection",
                    unit="rows",
                    leave=False,
                )

            for item in iterable_wrapped:
                if count >= sample_limit:
                    break
                count += 1

                # Flatten the item using dict_generator (same as iterable engine)
                try:
                    dk = dict_generator(item)
                    for i in dk:
                        # Skip invalid paths (same logic as iterable engine)
                        if len(i) == 0:
                            continue
                        if i[0].isdigit():
                            continue
                        if len(i[0]) == 1:
                            continue

                        # Build field path
                        k = ".".join(i[:-1])
                        v = i[-1]

                        # Only process fields we care about
                        if k not in field_paths:
                            continue

                        # Detect type (same as the iterable engine)
                        thetype = self.types.base(k, v)

                        # Update type distribution
                        if k not in type_distributions:
                            type_distributions[k] = {}
                        type_distributions[k][thetype] = type_distributions[k].get(thetype, 0) + 1
                except Exception as e:
                    # If processing this record fails, skip it
                    logger.debug(f"Failed to process sample record for type detection: {e}")
                    continue

        except Exception as e:
            # If sampling fails, log warning and continue with empty distributions
            logger.warning(f"Failed to sample records for type detection: {e}")
        finally:
            iterable.close()
            iterable_context.__exit__(None, None, None)

        return type_distributions

    def _compute_duckdb_dictionaries(
        self, fromfile, filetype, fielddata, finfields, dictshare, delimiter=None
    ):
        """Value frequencies of the low-cardinality fields, several fields per scan.

        Up to ``DICTIONARY_FIELDS_PER_SCAN`` fields are grouped in one scan with
        ``GROUPING SETS``; a scan that fails is repeated field by field.

        Args:
            fromfile: Path to input file
            filetype: File type ('csv', 'jsonl', 'json', etc.)
            fielddata: Dictionary of field statistics (used to identify low-cardinality fields)
            finfields: Dictionary mapping field paths to final types
            dictshare: Threshold percentage for dictionary construction (fields below this get dictionaries)
            delimiter: CSV delimiter (auto-detected when omitted)

        Returns:
            tuple: (field path -> {'items': {value: count}, 'count': n, 'type': field_type},
            field path -> exact number of distinct non-null values)
        """
        dictionaries = {}
        targets = []
        for field_path, fd in fielddata.items():
            if fd["share_uniq"] >= dictshare:
                continue
            quoted_field = self._quote_field_path(field_path)
            if quoted_field is None:
                dictionaries[field_path] = {
                    "items": {},
                    "count": 0,
                    "type": finfields.get(field_path, "str"),
                }
            else:
                targets.append((field_path, quoted_field))

        read_func = self._duckdb_read_func(fromfile, filetype, delimiter)
        counts: dict[str, list] = {field_path: [] for field_path, _ in targets}
        for first in range(0, len(targets), self.DICTIONARY_FIELDS_PER_SCAN):
            batch = targets[first : first + self.DICTIONARY_FIELDS_PER_SCAN]
            self._group_values(read_func, batch, counts)

        distinct = {}
        for field_path, _ in targets:
            distinct[field_path] = len(counts[field_path])
            # Most frequent first; values as text, like the iterable engine.
            items = {}
            for value, freq in sorted(counts[field_path], key=lambda pair: -pair[1]):
                items[str(value)] = int(freq)
            dictionaries[field_path] = {
                "items": items,
                "count": len(items),
                "type": finfields.get(field_path, "str"),
            }
        return dictionaries, distinct

    def _group_values(self, read_func, batch, counts):
        """Add ``(value, frequency)`` pairs of each field of ``batch`` to ``counts``."""
        width = len(batch)
        query = (
            f"SELECT {', '.join(f'GROUPING({q})' for _, q in batch)}, "
            f"{', '.join(q for _, q in batch)}, COUNT(*) FROM {read_func} "
            f"GROUP BY GROUPING SETS ({', '.join(f'({q})' for _, q in batch)})"
        )
        try:
            result = self._duckdb.execute(query)
            while rows := result.fetchmany(10_000):
                for row in rows:
                    index = row.index(0)  # GROUPING() is 0 for the field this row groups by
                    value = row[width + index]
                    if value is not None:
                        counts[batch[index][0]].append((value, row[-1]))
            return
        except duckdb.Error as exc:
            logger.debug("Grouping %d fields in one scan failed (%s)", width, exc)
        for field_path, quoted_field in batch:
            try:
                counts[field_path] = self._duckdb.execute(
                    f"SELECT {quoted_field}, COUNT(*) FROM {read_func} "
                    f"WHERE {quoted_field} IS NOT NULL GROUP BY {quoted_field}"
                ).fetchall()
            except duckdb.Error as field_exc:
                logger.debug(f"Failed to build dictionary for field {field_path}: {field_exc}")
                counts[field_path] = []

    def _stats_duckdb(self, fromfile, options):
        """Compute statistics using DuckDB engine.

        This is the main entry point for DuckDB-based statistics computation.
        It orchestrates all the DuckDB operations and combines results on one connection
        configured from ``--duckdb-threads``/``--duckdb-memory``/``--duckdb-temp-dir``
        (``--threads`` when no DuckDB thread count is given).

        Args:
            fromfile: Path to input file
            options: Dictionary of options (same as stats method)
        """
        self._duckdb_conn = duckdb_connection(options)
        try:
            return self._run_stats_duckdb(fromfile, options)
        finally:
            self._duckdb_conn.close()
            self._duckdb_conn = None

    def _run_stats_duckdb(self, fromfile, options):
        # Get progress control option (default: show progress)
        show_progress = get_option(options, "progress") is not False
        if "no_progress" in options and options["no_progress"]:
            show_progress = False

        # Detect file type if not provided
        filetype = get_option(options, "format_in")
        if filetype is None:
            ftype = detect_file_type(fromfile)
            if ftype["success"]:
                filetype = ftype["datatype"].id()

        if filetype is None:
            raise ValueError(f"Could not detect file type for {fromfile}")

        iterableargs = get_iterable_options(options)
        csv_delimiter = resolve_csv_delimiter(iterableargs, filename=fromfile, filetype=filetype)

        dictshare = get_option(options, "dictshare")
        if dictshare and str(dictshare).isdigit():
            dictshare = int(dictshare)
        else:
            dictshare = DEFAULT_DICT_SHARE

        # Fields and their DuckDB types (DESCRIBE reads a sample only)
        fields = self._describe_duckdb_fields(fromfile, filetype, csv_delimiter)
        if not fields:
            logger.warning(
                "DuckDB stats returned no fields from duckdb_decompose, falling back to iterable engine"
            )
            raise ValueError("No fields extracted - DuckDB returned empty result")
        field_paths = [field_path for field_path, _ in fields]

        # Types from a sample of records (same rules as the iterable engine)
        type_distributions = self._detect_types_from_sample(
            fromfile, filetype, field_paths, show_progress
        )
        fieldtypes = {
            field_path: {"key": field_path, "types": type_distributions.get(field_path, {})}
            for field_path in field_paths
        }

        for fd in fieldtypes.values():
            fd["types"].pop("empty", None)
        # Field types by the shared rules (the sample above stays in the debug output)
        finfields = dict.fromkeys(field_paths, "str")
        finfields.update(self._duckdb_field_types(fromfile, options, field_paths))
        numeric_paths = {
            path for path, ftype in finfields.items() if ftype in ("int", "float", "numeric")
        }

        # One scan: counts, missing values, estimated distinct values, lengths, distributions
        with (
            progress(desc="Computing statistics", unit="rows", leave=False, total=None)
            if show_progress
            else nullcontext()
        ):
            total_count, field_stats = self._compute_duckdb_profile(
                fromfile, filetype, field_paths, numeric_paths, csv_delimiter
            )
        fielddata = {}
        for field_path in field_paths:
            fielddata[field_path] = {
                "key": field_path,
                "uniq": {},
                "n_uniq": 0,
                "total": total_count,
                "share_uniq": 0.0,
                "minlen": None,
                "maxlen": 0,
                "avglen": 0.0,
                "totallen": 0,
            }
            fielddata[field_path].update(field_stats.get(field_path, {}))

        # Initialize profile structure
        profile = {"version": 1.0}
        profile["count"] = total_count
        profile["num_fields"] = len(fielddata)
        profile["fieldtypes"] = finfields

        # Value dictionaries of low-cardinality fields, which also give their exact distinct
        # counts; the other fields are counted in scans of bounded memory
        dictionaries, distinct = self._compute_duckdb_dictionaries(
            fromfile, filetype, fielddata, finfields, dictshare, csv_delimiter
        )
        others = {p: fielddata[p]["n_uniq"] for p in field_paths if p not in distinct}
        distinct.update(self._compute_duckdb_distinct(fromfile, filetype, others, csv_delimiter))
        if total_count:
            for field_path, count in distinct.items():
                fielddata[field_path]["cardinality_pct"] = round(count * 100.0 / total_count, 2)

        # Type inference (categorical vs numerical)
        type_inference = self._infer_field_types(fielddata, finfields)

        # Merge type inference into fielddata
        for field_path, inference in type_inference.items():
            if field_path in fielddata:
                fielddata[field_path]["type_category"] = inference["category"]
                fielddata[field_path]["is_categorical"] = inference["is_categorical"]
                fielddata[field_path]["is_numerical"] = inference["is_numerical"]

        # Build dictkeys list and populate dicts
        dictkeys = []
        dicts = {}
        profile["fields"] = []
        for fd in fielddata.values():
            field = {"key": fd["key"], "is_uniq": 0 if fd["share_uniq"] < 100 else 1}
            profile["fields"].append(field)
            if fd["share_uniq"] < dictshare:
                dictkeys.append(fd["key"])
                # Use dictionary from DuckDB computation
                if fd["key"] in dictionaries:
                    dicts[fd["key"]] = dictionaries[fd["key"]]
                else:
                    # Fallback if dictionary construction failed
                    field_type = finfields.get(fd["key"], "str")
                    dicts[fd["key"]] = {"items": {}, "count": fd["n_uniq"], "type": field_type}

        profile["dictkeys"] = dictkeys
        profile["dicts"] = dicts  # Store dictionaries in profile (though not displayed in table)

        # The iterable engine keeps uniq dictionaries in fielddata and deletes them at the end
        for value in fielddata.values():
            value.pop("uniq", None)

        profile["debug"] = {"fieldtypes": fieldtypes.copy(), "fielddata": fielddata, "dicts": dicts}

        # Display enhanced statistics table with profiling metrics
        if not get_option(options, "quiet"):
            self._display_enhanced_statistics_table(fielddata, finfields, dictkeys)
        return profile
