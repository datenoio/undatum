"""DuckDB-backed statistics computations (mixin)."""

import logging

import duckdb
from iterable.helpers.detect import detect_file_type

from ...common.command_utils import (
    duckdb_read_csv_expr,
    get_iterable_options,
    resolve_csv_delimiter,
)
from ...common.progress import progress
from ...common.s3_iterable import open_iterable_with_s3
from ...common.schema_utils import duckdb_decompose
from ...constants import DEFAULT_DICT_SHARE
from ...utils import dict_generator, get_option

logger = logging.getLogger(__name__)


class DuckDBStatsMixin:
    """DuckDB statistics engine methods for StatProcessor."""

    def _compute_duckdb_basic_stats(self, fromfile, filetype, delimiter=None):
        """Compute basic statistics using DuckDB's duckdb_decompose with summarize.

        Args:
            fromfile: Path to input file
            filetype: File type ('csv', 'jsonl', 'json', etc.)
            delimiter: CSV delimiter (auto-detected when omitted)

        Returns:
            tuple: (fielddata, fieldtypes, total_count) dictionaries matching iterable format
                - fielddata: Dict mapping field paths to statistics dicts
                - fieldtypes: Dict mapping field paths to type distribution dicts
                - total_count: Total number of records
        """
        # Call duckdb_decompose with use_summarize=True to get statistics
        # Use default limit (10000000) to process all rows - don't pass None as it creates invalid SQL
        columns_raw = duckdb_decompose(
            filename=fromfile,
            filetype=filetype,
            path="*",
            limit=10000000,  # Process all rows (default limit)
            recursive=True,
            ignore_errors=True,
            use_summarize=True,
            delimiter=delimiter,
        )

        fielddata = {}
        fieldtypes = {}
        total_count = 0

        # Log if columns_raw is empty to help debug
        if not columns_raw:
            logger.debug("duckdb_decompose returned empty result - no columns found")

        # Process results from duckdb_decompose
        # Format: [field_path, base_type, is_array, unique_count, total_count, uniqueness_percentage]
        for column in columns_raw:
            if len(column) < 6:
                continue  # Skip incomplete entries

            field_path = column[0]
            base_type = column[1]

            # Safely extract unique_count and total_count
            try:
                # column[3] and column[4] should be strings from duckdb_decompose
                unique_count_str = str(column[3]) if column[3] is not None else "0"
                count_str = str(column[4]) if column[4] is not None else "0"
                unique_count = int(unique_count_str) if unique_count_str.isdigit() else 0
                count = int(count_str) if count_str.isdigit() else 0
            except (ValueError, TypeError, IndexError, AttributeError):
                unique_count = 0
                count = 0

            try:
                uniqueness_percentage = float(column[5]) if column[5] else 0.0
            except (ValueError, TypeError, IndexError):
                uniqueness_percentage = 0.0

            # Track maximum total count (should be same for all fields, but use max)
            total_count = max(total_count, count)

            # Skip fields with empty names, None values, or invalid paths
            if not field_path or not isinstance(field_path, str) or field_path == "None":
                continue
            if field_path.startswith(".") or (field_path and field_path[0].isdigit()):
                continue

            # Initialize fielddata structure matching iterable format
            if field_path not in fielddata:
                fielddata[field_path] = {
                    "key": field_path,
                    "uniq": {},  # Will be populated later by dictionary construction
                    "n_uniq": unique_count,
                    "total": count,
                    "share_uniq": uniqueness_percentage,
                    "minlen": None,  # Will be computed separately
                    "maxlen": 0,
                    "avglen": 0.0,
                    "totallen": 0,
                }

            # Initialize fieldtypes structure
            # Map DuckDB types to our type system
            # Note: We'll do proper type detection from samples later, this is just initial
            if field_path not in fieldtypes:
                # Map DuckDB types to our type names
                type_mapping = {
                    "VARCHAR": "str",
                    "BIGINT": "int",
                    "INTEGER": "int",
                    "DOUBLE": "float",
                    "FLOAT": "float",
                    "BOOLEAN": "bool",
                    "DATE": "date",
                    "TIMESTAMP": "date",
                    "JSON": "str",  # JSON fields treated as strings initially
                }
                mapped_type = type_mapping.get(base_type, "str")

                fieldtypes[field_path] = {
                    "key": field_path,
                    "types": {mapped_type: count},  # Initial type distribution
                }

        return fielddata, fieldtypes, total_count

    def _compute_duckdb_length_stats(self, fromfile, filetype, field_paths, delimiter=None):
        """Compute length statistics (minlen, maxlen, avglen) for each field using DuckDB.

        Args:
            fromfile: Path to input file
            filetype: File type ('csv', 'jsonl', 'json', etc.)
            delimiter: CSV delimiter (auto-detected when omitted)
            field_paths: List of field paths to compute length statistics for

        Returns:
            dict: Mapping from field_path to dict with 'minlen', 'maxlen', 'avglen' keys
        """
        length_stats = {}

        # Determine read function based on file type
        if filetype in ["csv", "tsv"]:
            read_func = duckdb_read_csv_expr(fromfile, delimiter)
        elif filetype in ["json", "jsonl"]:
            read_func = f"read_json('{fromfile}', ignore_errors=true)"
        else:
            # For other formats (like Parquet), use direct table reference
            read_func = f"'{fromfile}'"

        # Compute length statistics for each field path
        for field_path in field_paths:
            # Skip None, empty, or invalid field paths
            if (
                not field_path
                or not isinstance(field_path, str)
                or field_path == "None"
                or field_path.startswith(".")
                or (field_path and field_path[0].isdigit())
            ):
                logger.debug(f"Skipping invalid field path: {field_path}")
                continue
            try:
                # Handle nested field paths - quote properly for SQL
                # For nested paths like "user.address.city", we need to access via dot notation
                # In DuckDB, we use bracket notation for nested fields: "user"."address"."city"
                field_parts = field_path.split(".")
                # Validate that no path part is None or "None"
                if any(
                    not part or part == "None" or not isinstance(part, str) for part in field_parts
                ):
                    logger.debug(f"Skipping field path with invalid parts: {field_path}")
                    continue

                if len(field_parts) == 1:
                    # Simple field path
                    quoted_field = f'"{field_path}"'
                else:
                    # Nested field path - construct path expression
                    # For DuckDB JSON, we might need to use JSON extraction
                    # For CSV with nested structures, this won't work directly
                    # Let's try the bracket notation approach first
                    quoted_field = ".".join([f'"{part}"' for part in field_parts])

                # Construct SQL query to compute length statistics
                # Cast to VARCHAR first, then compute length
                # Handle NULL values - only compute length for non-NULL values
                query = f"""
                SELECT
                    MIN(CASE WHEN {quoted_field} IS NOT NULL THEN LENGTH(CAST({quoted_field} AS VARCHAR)) ELSE NULL END) as minlen,
                    MAX(CASE WHEN {quoted_field} IS NOT NULL THEN LENGTH(CAST({quoted_field} AS VARCHAR)) ELSE NULL END) as maxlen,
                    AVG(CASE WHEN {quoted_field} IS NOT NULL THEN LENGTH(CAST({quoted_field} AS VARCHAR)) ELSE NULL END) as avglen,
                    COUNT(*) as total_count
                FROM {read_func}
                """

                # Execute query
                result = duckdb.sql(query).fetchone()

                if result:
                    minlen, maxlen, avglen, total_count = result
                    length_stats[field_path] = {
                        "minlen": int(minlen) if minlen is not None else None,
                        "maxlen": int(maxlen) if maxlen is not None else 0,
                        "avglen": float(avglen) if avglen is not None else 0.0,
                        "total_count": int(total_count) if total_count else 0,
                    }
                else:
                    # No results, set defaults
                    length_stats[field_path] = {
                        "minlen": None,
                        "maxlen": 0,
                        "avglen": 0.0,
                        "total_count": 0,
                    }
            except Exception as e:
                # If query fails for this field, log and continue with defaults
                logger.debug(f"Failed to compute length stats for field {field_path}: {e}")
                length_stats[field_path] = {
                    "minlen": None,
                    "maxlen": 0,
                    "avglen": 0.0,
                    "total_count": 0,
                }

        return length_stats

    @staticmethod
    def _duckdb_read_func(fromfile, filetype, delimiter=None):
        """Build a DuckDB read function expression for the given file."""
        if filetype in ["csv", "tsv"]:
            return duckdb_read_csv_expr(fromfile, delimiter)
        if filetype in ["json", "jsonl"]:
            return f"read_json('{fromfile}', ignore_errors=true)"
        return f"'{fromfile}'"

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

    def _compute_duckdb_missing_values(
        self, fromfile, filetype, field_paths, total_count, delimiter=None
    ):
        """Compute missing value counts and cardinality for each field using DuckDB.

        Args:
            fromfile: Path to input file
            filetype: File type ('csv', 'jsonl', 'json', etc.)
            delimiter: CSV delimiter (auto-detected when omitted)
            field_paths: List of field paths to compute statistics for
            total_count: Total number of records in the dataset

        Returns:
            dict: Mapping from field_path to dict with 'missing_count',
                'missing_rate' and 'cardinality_pct' keys
        """
        missing_stats = {}
        read_func = self._duckdb_read_func(fromfile, filetype, delimiter)

        for field_path in field_paths:
            quoted_field = self._quote_field_path(field_path)
            if quoted_field is None:
                logger.debug(f"Skipping invalid field path: {field_path}")
                continue
            try:
                query = f"""
                SELECT
                    COUNT(*) - COUNT({quoted_field}) as missing_count,
                    COUNT(DISTINCT {quoted_field}) as n_uniq,
                    COUNT(*) as total
                FROM {read_func}
                """
                result = duckdb.sql(query).fetchone()
                if result:
                    missing_count, n_uniq, total = result
                    total = total or total_count or 0
                    missing_stats[field_path] = {
                        "missing_count": int(missing_count or 0),
                        "missing_rate": (
                            round((missing_count or 0) * 100.0 / total, 2) if total else 0.0
                        ),
                        "cardinality_pct": (
                            round((n_uniq or 0) * 100.0 / total, 2) if total else 0.0
                        ),
                    }
            except Exception as e:
                logger.debug(f"Failed to compute missing values for field {field_path}: {e}")

        return missing_stats

    def _compute_duckdb_distributions(
        self, fromfile, filetype, field_paths, finfields, delimiter=None
    ):
        """Compute distribution statistics (mean, median, min, max, stddev) for numerical fields.

        Args:
            fromfile: Path to input file
            filetype: File type ('csv', 'jsonl', 'json', etc.)
            delimiter: CSV delimiter (auto-detected when omitted)
            field_paths: List of field paths
            finfields: Dictionary mapping field paths to final types

        Returns:
            dict: Mapping from field_path to dict with 'min', 'max', 'mean',
                'median' and 'stddev' keys (numerical fields only)
        """
        distribution_stats = {}
        read_func = self._duckdb_read_func(fromfile, filetype, delimiter)

        for field_path in field_paths:
            if finfields.get(field_path) not in ("int", "float", "numeric"):
                continue
            quoted_field = self._quote_field_path(field_path)
            if quoted_field is None:
                continue
            try:
                numeric_expr = f"TRY_CAST({quoted_field} AS DOUBLE)"
                query = f"""
                SELECT
                    MIN({numeric_expr}) as min_val,
                    MAX({numeric_expr}) as max_val,
                    AVG({numeric_expr}) as mean_val,
                    MEDIAN({numeric_expr}) as median_val,
                    STDDEV({numeric_expr}) as stddev_val
                FROM {read_func}
                """
                result = duckdb.sql(query).fetchone()
                if result and result[2] is not None:
                    min_val, max_val, mean_val, median_val, stddev_val = result
                    distribution_stats[field_path] = {
                        "min": float(min_val) if min_val is not None else None,
                        "max": float(max_val) if max_val is not None else None,
                        "mean": float(mean_val) if mean_val is not None else None,
                        "median": float(median_val) if median_val is not None else None,
                        "stddev": float(stddev_val) if stddev_val is not None else None,
                    }
            except Exception as e:
                logger.debug(f"Failed to compute distribution stats for field {field_path}: {e}")

        return distribution_stats

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
        """Compute value frequency dictionaries for low-cardinality fields using DuckDB GROUP BY.

        Args:
            fromfile: Path to input file
            filetype: File type ('csv', 'jsonl', 'json', etc.)
            delimiter: CSV delimiter (auto-detected when omitted)
            fielddata: Dictionary of field statistics (used to identify low-cardinality fields)
            finfields: Dictionary mapping field paths to final types
            dictshare: Threshold percentage for dictionary construction (fields below this get dictionaries)

        Returns:
            dict: Mapping from field_path to dictionary structure {'items': {value: count}, 'count': n_uniq, 'type': field_type}
        """
        dictionaries = {}

        # Determine read function based on file type
        if filetype in ["csv", "tsv"]:
            read_func = duckdb_read_csv_expr(fromfile, delimiter)
        elif filetype in ["json", "jsonl"]:
            read_func = f"read_json('{fromfile}', ignore_errors=true)"
        else:
            read_func = f"'{fromfile}'"

        # Identify fields that need dictionaries (uniqueness percentage below dictshare)
        for field_path, fd in fielddata.items():
            if fd["share_uniq"] >= dictshare:
                continue  # Skip high-cardinality fields

            # Skip None, empty, or invalid field paths
            if (
                not field_path
                or not isinstance(field_path, str)
                or field_path == "None"
                or field_path.startswith(".")
                or (field_path and field_path[0].isdigit())
            ):
                logger.debug(f"Skipping invalid field path for dictionary: {field_path}")
                # Create empty dictionary entry
                field_type = finfields.get(field_path, "str")
                dictionaries[field_path] = {"items": {}, "count": 0, "type": field_type}
                continue

            try:
                # Construct field reference for SQL query
                field_parts = field_path.split(".")
                # Validate that no path part is None or "None"
                if any(
                    not part or part == "None" or not isinstance(part, str) for part in field_parts
                ):
                    logger.debug(f"Skipping dictionary field path with invalid parts: {field_path}")
                    # Create empty dictionary entry
                    field_type = finfields.get(field_path, "str")
                    dictionaries[field_path] = {"items": {}, "count": 0, "type": field_type}
                    continue

                if len(field_parts) == 1:
                    # Simple field path - just quote it
                    quoted_field = f'"{field_path}"'
                else:
                    # Nested field path - use dot notation with quoted parts
                    quoted_field = ".".join([f'"{part}"' for part in field_parts])

                # Construct SQL query to get value frequencies
                # SELECT field_value, COUNT(*) as freq FROM ... GROUP BY field_value ORDER BY freq DESC
                query = f"""
                SELECT
                    {quoted_field} as value,
                    COUNT(*) as freq
                FROM {read_func}
                WHERE {quoted_field} IS NOT NULL
                GROUP BY {quoted_field}
                ORDER BY freq DESC
                """

                # Execute query and fetch all results
                results = duckdb.sql(query).fetchall()

                # Build dictionary structure matching iterable engine format
                items_dict = {}
                for value, freq in results:
                    # Convert value to string for consistency with iterable engine
                    value_str = str(value) if value is not None else ""
                    items_dict[value_str] = int(freq)

                # Get field type and unique count
                field_type = finfields.get(field_path, "str")
                n_uniq = len(items_dict)

                # Build dictionary structure
                dictionaries[field_path] = {
                    "items": items_dict,
                    "count": n_uniq,
                    "type": field_type,
                }

            except Exception as e:
                # If dictionary construction fails for this field, log and skip
                logger.debug(f"Failed to build dictionary for field {field_path}: {e}")
                # Create empty dictionary entry
                field_type = finfields.get(field_path, "str")
                dictionaries[field_path] = {"items": {}, "count": 0, "type": field_type}

        return dictionaries

    def _stats_duckdb(self, fromfile, options):
        """Compute statistics using DuckDB engine.

        This is the main entry point for DuckDB-based statistics computation.
        It orchestrates all the DuckDB operations and combines results.

        Args:
            fromfile: Path to input file
            options: Dictionary of options (same as stats method)
        """
        # Get progress control option (default: show progress)
        show_progress = get_option(options, "progress") is not False
        if "no_progress" in options and options["no_progress"]:
            show_progress = False

        # Honor --threads on the default DuckDB connection
        threads = get_option(options, "threads") or get_option(options, "duckdb_threads")
        if threads:
            duckdb.sql(f"SET threads={int(threads)}")

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

        # Phase 0: Count rows for progress indication (fast COUNT query)
        total_count = 0
        if show_progress:
            try:
                if filetype in ["json", "jsonl"]:
                    query_str = f"SELECT COUNT(*) FROM read_json('{fromfile}', ignore_errors=true)"
                elif filetype in ["csv", "tsv"]:
                    query_str = (
                        f"SELECT COUNT(*) FROM {duckdb_read_csv_expr(fromfile, csv_delimiter)}"
                    )
                else:
                    query_str = f"SELECT COUNT(*) FROM '{fromfile}'"
                with progress(desc="Counting rows", unit="rows", leave=False, total=None) as pbar:
                    total_count = duckdb.sql(query_str).fetchone()[0]
                    pbar.total = total_count
                    pbar.update(total_count)
            except Exception as e:
                logger.debug(f"Failed to count rows for progress: {e}")

        # Phase 1: Get basic statistics using duckdb_decompose
        if show_progress and total_count > 0:
            with progress(
                desc="Computing statistics",
                unit="rows",
                total=total_count,
                initial=total_count,
                leave=False,
            ) as pbar:
                fielddata, fieldtypes, computed_count = self._compute_duckdb_basic_stats(
                    fromfile, filetype, csv_delimiter
                )
                # Use computed count if we didn't get it from Phase 0
                if total_count == 0:
                    total_count = computed_count
                    pbar.total = total_count
                # Mark statistics computation as complete
                pbar.update(0)  # Already at total, just refresh display
        else:
            fielddata, fieldtypes, computed_count = self._compute_duckdb_basic_stats(
                fromfile, filetype, csv_delimiter
            )
            if total_count == 0:
                total_count = computed_count

        # Check if we got any fields - if empty, fall back to iterable
        if not fielddata:
            logger.warning(
                "DuckDB stats returned no fields from duckdb_decompose, falling back to iterable engine"
            )
            raise ValueError("No fields extracted - DuckDB returned empty result")

        # Phase 2: Filter out None, empty, or invalid field paths before processing
        field_paths = [
            fp
            for fp in fielddata.keys()
            if fp
            and isinstance(fp, str)
            and fp != "None"
            and not fp.startswith(".")
            and not fp[0].isdigit()
        ]

        # Phase 3: Compute missing values and cardinality
        missing_stats = self._compute_duckdb_missing_values(
            fromfile, filetype, field_paths, total_count, csv_delimiter
        )

        # Merge missing value statistics into fielddata
        for field_path, stats in missing_stats.items():
            if field_path in fielddata:
                fielddata[field_path]["missing_count"] = stats["missing_count"]
                fielddata[field_path]["missing_rate"] = stats["missing_rate"]
                fielddata[field_path]["cardinality_pct"] = stats["cardinality_pct"]

        # Phase 4: Compute length statistics (minlen, maxlen, avglen)
        length_stats = self._compute_duckdb_length_stats(
            fromfile, filetype, field_paths, csv_delimiter
        )

        # Merge length statistics into fielddata
        for field_path, stats in length_stats.items():
            if field_path in fielddata:
                fielddata[field_path]["minlen"] = stats["minlen"]
                fielddata[field_path]["maxlen"] = stats["maxlen"]
                fielddata[field_path]["avglen"] = stats["avglen"]
                # Calculate totallen for consistency (avglen * total)
                if stats["avglen"] and stats["total_count"]:
                    fielddata[field_path]["totallen"] = int(stats["avglen"] * stats["total_count"])

        # Phase 5: Type detection from samples (hybrid approach)
        type_distributions = self._detect_types_from_sample(
            fromfile, filetype, field_paths, show_progress
        )

        # Merge type distributions into fieldtypes
        for field_path, type_dist in type_distributions.items():
            if field_path in fieldtypes:
                # Update fieldtypes with sampled type distribution
                fieldtypes[field_path]["types"] = type_dist
            else:
                # Create new entry if not found
                fieldtypes[field_path] = {"key": field_path, "types": type_dist}

        # Initialize profile structure
        profile = {"version": 1.0}
        profile["count"] = total_count
        profile["num_fields"] = len(fielddata)

        # Determine final field types (matching iterable logic)
        finfields = {}
        for fd in fieldtypes.values():
            fdt = list(fd["types"].keys())
            if "empty" in fdt:
                del fd["types"]["empty"]
            types_keys = list(fd["types"].keys())
            if len(types_keys) != 1:
                ftype = "str"
            else:
                ftype = types_keys[0]
            finfields[fd["key"]] = ftype

        profile["fieldtypes"] = finfields

        # Phase 6: Compute distribution statistics for numerical fields
        distribution_stats = self._compute_duckdb_distributions(
            fromfile, filetype, field_paths, finfields, csv_delimiter
        )

        # Merge distribution statistics into fielddata
        for field_path, stats in distribution_stats.items():
            if field_path in fielddata:
                fielddata[field_path].update(stats)

        # Phase 7: Type inference (categorical vs numerical)
        type_inference = self._infer_field_types(fielddata, finfields)

        # Merge type inference into fielddata
        for field_path, inference in type_inference.items():
            if field_path in fielddata:
                fielddata[field_path]["type_category"] = inference["category"]
                fielddata[field_path]["is_categorical"] = inference["is_categorical"]
                fielddata[field_path]["is_numerical"] = inference["is_numerical"]

        # Phase 8: Dictionary construction for low-cardinality fields
        dictionaries = self._compute_duckdb_dictionaries(
            fromfile, filetype, fielddata, finfields, dictshare, csv_delimiter
        )

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

        # Store dictionaries in fielddata for compatibility with iterable engine output format
        # Note: The iterable engine stores uniq dictionaries in fielddata and then deletes them
        # We're building them separately but need to clean up the structure
        for k, v in fielddata.items():
            if "uniq" in v:
                del v["uniq"]
            fielddata[k] = v

        profile["debug"] = {"fieldtypes": fieldtypes.copy(), "fielddata": fielddata, "dicts": dicts}

        # Display enhanced statistics table with profiling metrics
        if not get_option(options, "quiet"):
            self._display_enhanced_statistics_table(fielddata, finfields, dictkeys)
        return profile
