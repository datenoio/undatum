"""Fluent, lazy ``Dataset`` API over the operation registry.

A ``Dataset`` is an immutable plan: a source plus a tuple of operation calls. Transform
methods return a new ``Dataset`` with one more step and read nothing. The plan runs when
results are needed — iteration, :meth:`Dataset.write`, :meth:`Dataset.count`,
:meth:`Dataset.stats`, DataFrame export — and records stream from step to step as Python
objects (no intermediate files, types preserved). Writing a plan whose every step has a
DuckDB form on a DuckDB-readable source runs as a single query.
"""

from __future__ import annotations

import itertools
import logging
import os
import tempfile
from collections import Counter, deque
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from ..io import RowSource, side_options
from ..ops import (
    CatConfig,
    DedupConfig,
    EnumConfig,
    ExcludeConfig,
    ExplodeConfig,
    FillConfig,
    FixLengthsConfig,
    HeadConfig,
    JoinConfig,
    MaskConfig,
    RenameConfig,
    ReplaceConfig,
    ReverseConfig,
    SampleConfig,
    SearchConfig,
    SelectConfig,
    SliceConfig,
    SortConfig,
    TransposeConfig,
    get_operation,
    write_query,
    write_rows,
)
from .results import QueryResult, StatsResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceSpec:
    """Where the records of a plan come from: a path/URI or in-memory records."""

    path: str | None = None
    records: Sequence[Any] | Iterable[Any] | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OperationCall:
    """One step of a plan: a registered operation and its configuration."""

    name: str
    config: Any


def _as_tuple(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


class Dataset:
    """Lazy, chainable dataset.

    Example:
        >>> from undatum import Dataset
        >>> ds = Dataset.read("data.jsonl")
        >>> ds = ds.fill("age", value=0).dedup(keys=["user_id"])
        >>> stats = ds.stats()
        >>> ds.write("output.parquet")
    """

    def __init__(
        self,
        source: str | None = None,
        data: Iterable[dict] | None = None,
        options: dict | None = None,
        *,
        steps: tuple[OperationCall, ...] = (),
    ):
        """Create a dataset from a path (``source``) or records (``data``).

        Prefer :meth:`read` and :meth:`from_records`. A one-shot iterator passed as
        ``data`` can be consumed once; pass a list to iterate the dataset several times.
        """
        self._spec = SourceSpec(path=source, records=data, options=dict(options or {}))
        self._steps = steps

    # ------------------------------------------------------------------- sources

    @classmethod
    def read(cls, path: str, **options: Any) -> Dataset:
        """Read data from a file or cloud URI.

        Args:
            path: File path or cloud URI (s3://, gs://, az://, ...)
            **options: Reader options (encoding, delimiter, format_in, table, flatten_nested,
                on_error, ...)

        Returns:
            Dataset instance

        Example:
            >>> ds = Dataset.read("data.csv")
            >>> ds = Dataset.read("s3://bucket/data.jsonl", encoding="utf8")
            >>> ds = Dataset.read("workbook.xlsx", table="Sheet2")
            >>> ds = Dataset.read("nested.jsonl", flatten_nested=True)
        """
        return cls(source=path, options=options)

    @classmethod
    def from_records(cls, records: Iterable[dict]) -> Dataset:
        """Wrap in-memory records (a list can be iterated any number of times).

        Example:
            >>> Dataset.from_records([{"a": 1}, {"a": 2}]).count()
            2
        """
        return cls(data=records)

    def _then(self, name: str, config: Any) -> Dataset:
        get_operation(name)  # unknown names fail when the step is added
        spec = self._spec
        return Dataset(
            spec.path, spec.records, spec.options, steps=(*self._steps, OperationCall(name, config))
        )

    @property
    def source(self) -> str | None:
        """Path or URI the records are read from (``None`` for in-memory records)."""
        return self._spec.path

    @property
    def steps(self) -> tuple[OperationCall, ...]:
        """The operations of the plan, in order."""
        return self._steps

    def explain(self) -> str:
        """Describe the plan, one line per step."""
        source = self._spec.path or "<records>"
        lines = [f"read {source}"]
        lines += [f"{call.name} {call.config}" for call in self._steps]
        return "\n".join(lines)

    # ---------------------------------------------------------------- execution

    def _source_rows(self, extra: dict | None = None) -> Iterable[Any]:
        spec = self._spec
        options = {**spec.options, **(extra or {})}
        if spec.path is not None:
            return RowSource(spec.path, options)
        if spec.records is not None:
            from ..common.command_utils import iter_command_rows

            records = spec.records
            if options.get("flatten_nested"):
                return list(iter_command_rows(records, options))
            return records
        raise ValueError("No data source available")

    def _rows(self, extra: dict | None = None) -> Iterator[Any]:
        rows: Iterable[Any] = self._source_rows(extra)
        for call in self._steps:
            rows = get_operation(call.name).apply(rows, call.config)
        return iter(rows)

    def __iter__(self) -> Iterator[dict]:
        """Run the plan and yield its records."""
        return self._rows()

    def collect(self) -> QueryResult:
        """Run the plan and return every record as a list."""
        return QueryResult(self._rows())

    def _sql_query(self, conn: Any) -> str | None:
        """Compose the plan into one DuckDB query, or ``None`` when a step has no SQL form."""
        if not self._steps or self._spec.path is None:
            return None
        relation = RowSource(self._spec.path, self._spec.options).duckdb_from()
        if relation is None:
            return None
        query = f"SELECT * FROM {relation}"
        for call in self._steps:
            described = conn.sql(f"DESCRIBE {query}").fetchall()
            schema = {row[0]: str(row[1]).upper() for row in described}
            sql = get_operation(call.name).to_sql(f"({query})", schema, call.config)
            if sql is None:
                return None
            query = sql
        return query

    def write(self, path: str, **options: Any) -> None:
        """Write dataset to a file or cloud URI.

        Args:
            path: Output file path or cloud URI (s3://, gs://, az://, ...)
            **options: Output options (``format_out``; for a plain conversion without
                steps also ``compression``, ``level``, ``profile``, ...)

        Example:
            >>> ds.write("output.jsonl")
            >>> ds.write("s3://bucket/output.parquet", format_out="parquet")
            >>> ds.write("az://container/output.csv")
        """
        format_out = options.get("format_out")
        if not self._steps and self._spec.path is not None:
            from ..cmds.converter import Converter

            Converter().convert(self._spec.path, path, {**self._spec.options, **options})
            return
        if self._spec.path is not None:
            written = self._write_sql(path, format_out)
            if written:
                return
        write_rows(self._rows(), path, format_out=format_out)

    def _write_sql(self, path: str, format_out: str | None) -> bool:
        try:
            import duckdb

            from ..common.duckdb_config import create_duckdb_connection

            conn = create_duckdb_connection(threads=1, memory="256MB")
        except Exception:  # pragma: no cover - DuckDB missing or misconfigured
            return False
        try:
            query = self._sql_query(conn)
            if query is None:
                return False
            logger.debug("Dataset.write: DuckDB plan: %s", query)
            write_query(conn, query, path, format_out)
            return True
        except duckdb.Error as exc:
            logger.warning("DuckDB plan failed, using the Python engine: %s", exc)
            return False
        finally:
            conn.close()

    def close(self) -> None:
        """Release resources (kept for compatibility; plans create no temporary files)."""

    def __enter__(self) -> Dataset:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------- transforms

    def fill(
        self,
        fields: str | list[str] | None = None,
        value: Any = None,
        strategy: str | None = None,
        **options: Any,
    ) -> Dataset:
        """Fill empty or null values.

        Args:
            fields: Field name(s) to fill (all fields when ``None``)
            value: Constant value (and fallback for ``forward``/``backward``)
            strategy: ``constant`` (default), ``forward`` or ``backward``
            **options: Ignored (kept for compatibility)

        Returns:
            New Dataset with the step added

        Example:
            >>> ds = ds.fill("age", value=0)
            >>> ds = ds.fill(["name", "email"], value="N/A")
            >>> ds = ds.fill("status", strategy="forward")
        """
        names = _as_tuple(fields)
        return self._then(
            "fill",
            FillConfig(
                fields=names or None,
                strategy=strategy or "constant",
                value="" if value is None else value,
            ),
        )

    def dedup(self, keys: list[str] | None = None, keep: str = "first", **options: Any) -> Dataset:
        """Remove duplicate records.

        Args:
            keys: Key fields (all fields when ``None``)
            keep: ``first`` or ``last``
            **options: ``low_memory``, ``temp_dir``

        Returns:
            New Dataset with the step added

        Example:
            >>> ds = ds.dedup(keys=["user_id"])
        """
        if keep not in ("first", "last"):
            raise ValueError("keep must be 'first' or 'last'")
        return self._then(
            "dedup",
            DedupConfig(
                keys=_as_tuple(keys),
                keep=keep,
                low_memory=bool(options.get("low_memory")),
                temp_dir=options.get("temp_dir"),
            ),
        )

    def sort(
        self,
        by: str | list[str],
        desc: bool = False,
        numeric: bool | list[str] = False,
        **options: Any,
    ) -> Dataset:
        """Sort records (stable; external merge sort above 100,000 records).

        Args:
            by: Field name(s) to sort by
            desc: Descending order
            numeric: ``True`` to compare every ``by`` field as a number, or a list of fields
            **options: ``temp_dir`` for merge runs

        Returns:
            New Dataset with the step added

        Example:
            >>> ds = ds.sort("age", desc=True, numeric=True)
        """
        fields = _as_tuple(by)
        numeric_fields = fields if numeric is True else _as_tuple(numeric or None)
        return self._then(
            "sort",
            SortConfig(
                by=fields, desc=desc, numeric=numeric_fields, temp_dir=options.get("temp_dir")
            ),
        )

    def filter(
        self,
        pattern: str | None = None,
        fields: list[str] | None = None,
        query: str | None = None,
        **options: Any,
    ) -> Dataset:
        """Keep records matching a regular expression or a comparison expression.

        Args:
            pattern: Regular expression searched in ``fields`` (all fields when ``None``)
            fields: Fields searched by ``pattern``
            query: Comparison expression such as ``age > 30 AND city == "Berlin"``
            **options: ``ignore_case`` for ``pattern``

        Returns:
            New Dataset with the step added

        Example:
            >>> ds = ds.filter(pattern="error", fields=["message"])
            >>> ds = ds.filter(query="age > 30")
        """
        if pattern:
            import re

            re.compile(pattern)
            return self._then(
                "search",
                SearchConfig(
                    pattern=pattern,
                    fields=_as_tuple(fields) or None,
                    ignore_case=bool(options.get("ignore_case")),
                ),
            )
        if query:
            return self._then("select", SelectConfig(filter=query))
        raise ValueError("filter requires pattern= or query=")

    def select(
        self, fields: str | list[str], filter_expr: str | None = None, **options: Any
    ) -> Dataset:
        """Keep some fields (dotted paths keep nested values) and optionally filter.

        Args:
            fields: Field name(s) to keep
            filter_expr: Optional comparison expression
            **options: ``output`` writes the result there right away (compatibility)

        Returns:
            New Dataset with the step added

        Example:
            >>> ds = ds.select(["name", "email"], filter_expr="age > 30")
        """
        dataset = self._then("select", SelectConfig(fields=_as_tuple(fields), filter=filter_expr))
        output = options.get("output")
        if output:
            dataset.write(output)
            return Dataset.read(output)
        return dataset

    def join(
        self,
        other: Dataset | str,
        keys: str | list[str],
        join_type: str = "inner",
        **options: Any,
    ) -> Dataset:
        """Hash join with another dataset or file (the other side is held in memory).

        Args:
            other: Dataset or file path
            keys: Join key field(s)
            join_type: ``inner``, ``left``, ``right`` or ``full``
            **options: Reader options for ``other`` when it is a path (``table2``, ...)

        Returns:
            New Dataset with the step added

        Example:
            >>> ds = ds1.join(ds2, keys=["user_id"], join_type="left")
        """
        if join_type not in ("inner", "left", "right", "full", "outer"):
            raise ValueError(f"Unknown join type '{join_type}'")
        right: Iterable[Any]
        if isinstance(other, Dataset):
            right = other
        else:
            right = RowSource(other, side_options({**self._spec.options, **options}, 2))
        return self._then("join", JoinConfig(right=right, on=_as_tuple(keys), how=join_type))

    def sample(self, n: int | None = None, percent: float | None = None, **options: Any) -> Dataset:
        """Random sample of ``n`` records or ``percent`` of them.

        Args:
            n: Number of records
            percent: Share of the records (0-100)
            **options: ``seed`` for a reproducible sample

        Returns:
            New Dataset with the step added

        Example:
            >>> ds = ds.sample(n=100, seed=1)
        """
        if not n and not percent:
            raise ValueError("sample requires n= or percent=")
        return self._then("sample", SampleConfig(size=n, percent=percent, seed=options.get("seed")))

    def mask(
        self,
        fields: str | list[str],
        method: str = "redact",
        salt: str | None = None,
        **options: Any,
    ) -> Dataset:
        """Mask sensitive fields.

        Args:
            fields: Field name(s) to mask
            method: ``redact``, ``hash`` or ``randomize``
            salt: Salt for ``hash``
            **options: Ignored (kept for compatibility)

        Returns:
            New Dataset with the step added

        Example:
            >>> ds = ds.mask(["email", "phone"], method="hash", salt="s3cret")
        """
        if method not in ("redact", "hash", "randomize"):
            raise ValueError(f"Unknown masking method '{method}'")
        return self._then("mask", MaskConfig(fields=_as_tuple(fields), method=method, salt=salt))

    def rename(
        self,
        mapping: dict[str, str] | None = None,
        pattern: str | None = None,
        replacement: str = "",
        **options: Any,
    ) -> Dataset:
        """Rename fields by exact mapping and/or a regular expression.

        Args:
            mapping: Dict of ``old_name`` to ``new_name``
            pattern: Regular expression matched against field names
            replacement: Replacement for ``pattern``
            **options: Ignored (kept for compatibility)

        Returns:
            New Dataset with the step added
        """
        if mapping is None and not pattern:
            raise ValueError("rename requires mapping= or pattern=")
        if pattern:
            import re

            re.compile(pattern)
        return self._then(
            "rename", RenameConfig(mapping=mapping, pattern=pattern, replacement=replacement)
        )

    def replace(
        self,
        field: str,
        pattern: str,
        replacement: str = "",
        *,
        regex: bool = False,
        global_replace: bool = True,
    ) -> Dataset:
        """Replace text in one field.

        Args:
            field: Field whose values change
            pattern: Text, or a regular expression with ``regex=True``
            replacement: Replacement text
            regex: Treat ``pattern`` as a regular expression
            global_replace: Replace every occurrence (default) or only the first

        Returns:
            New Dataset with the step added
        """
        if regex:
            import re

            re.compile(pattern)
        return self._then(
            "replace",
            ReplaceConfig(
                field=field,
                pattern=pattern,
                replacement=replacement,
                regex=regex,
                global_replace=global_replace,
            ),
        )

    def explode(self, field: str, separator: str = ",", **options: Any) -> Dataset:
        """One record per part of a delimited field.

        Args:
            field: Field to split
            separator: Separator (default: comma)
            **options: Ignored (kept for compatibility)

        Returns:
            New Dataset with the step added
        """
        return self._then("explode", ExplodeConfig(field=field, separator=separator))

    def enum(
        self,
        field: str = "row_id",
        enum_type: str = "number",
        start: int = 1,
        value: Any = None,
        **options: Any,
    ) -> Dataset:
        """Add row numbers, UUIDs or a constant field.

        Args:
            field: Field name for generated values (default: ``row_id``)
            enum_type: ``number``, ``uuid`` or ``constant``
            start: First number
            value: Constant for ``enum_type="constant"``
            **options: Ignored (kept for compatibility)

        Returns:
            New Dataset with the step added
        """
        return self._then("enum", EnumConfig(field=field, kind=enum_type, start=start, value=value))

    def reverse(self, **options: Any) -> Dataset:
        """Reverse record order (spills to disk for large inputs).

        Args:
            **options: Ignored (kept for compatibility)

        Returns:
            New Dataset with the step added
        """
        return self._then("reverse", ReverseConfig())

    def exclude(self, other: Dataset | str, on: str | list[str] | None = None) -> Dataset:
        """Drop records whose key appears in ``other``.

        Args:
            other: Dataset or file path with the keys to exclude
            on: Key fields (all fields when ``None``)

        Returns:
            New Dataset with the step added
        """
        excluded: Iterable[Any] = (
            other if isinstance(other, Dataset) else RowSource(other, self._spec.options)
        )
        return self._then("exclude", ExcludeConfig(exclude=excluded, on=_as_tuple(on)))

    def concat(self, *others: Dataset | str) -> Dataset:
        """Append the records of other datasets or files.

        Returns:
            New Dataset with the step added
        """
        sources = tuple(
            o if isinstance(o, Dataset) else RowSource(o, self._spec.options) for o in others
        )
        return self._then("cat", CatConfig(others=sources))

    def limit(self, n: int) -> Dataset:
        """Keep the first ``n`` records (lazy; :meth:`head` returns a list).

        Returns:
            New Dataset with the step added
        """
        return self._then("head", HeadConfig(limit=n))

    def slice(self, start: int = 0, end: int | None = None) -> Dataset:
        """Records ``start`` (inclusive) to ``end`` (exclusive), 0-based.

        Returns:
            New Dataset with the step added
        """
        return self._then("slice", SliceConfig(start=start, end=end))

    def fixlengths(self, strategy: str = "pad", value: Any = "") -> Dataset:
        """Give every record the same, alphabetically ordered fields.

        Args:
            strategy: ``pad`` or ``truncate``
            value: Value for missing fields

        Returns:
            New Dataset with the step added
        """
        return self._then("fixlengths", FixLengthsConfig(strategy=strategy, value=value))

    def transpose(self) -> Dataset:
        """One record per field: ``field`` plus ``row_0``, ``row_1``, ...

        Returns:
            New Dataset with the step added
        """
        return self._then("transpose", TransposeConfig())

    # --------------------------------------------------------------- terminals

    def count(self, **options: Any) -> int:
        """Number of records.

        Args:
            **options: Reader options applied for this call (e.g. ``flatten_nested``)

        Returns:
            Number of records

        Example:
            >>> Dataset.read("data.csv").count()
            1000
        """
        return sum(1 for _ in self._rows(options or None))

    def head(self, n: int = 10, **options: Any) -> list[dict]:
        """First ``n`` records.

        Args:
            n: Number of records
            **options: Reader options applied for this call

        Returns:
            List of records
        """
        return QueryResult(itertools.islice(self._rows(options or None), n))

    def tail(self, n: int = 10, **options: Any) -> list[dict]:
        """Last ``n`` records.

        Args:
            n: Number of records
            **options: Reader options applied for this call

        Returns:
            List of records
        """
        return QueryResult(deque(self._rows(options or None), maxlen=n))

    def uniq(self, fields: str | list[str]) -> list[dict]:
        """Distinct combinations of ``fields``, in first-seen order.

        Returns:
            List of dicts with the field values
        """
        names = _as_tuple(fields)
        seen: dict[str, dict[str, Any]] = {}
        for row in self._rows():
            if isinstance(row, dict):
                values = {name: row.get(name) for name in names}
                seen.setdefault(repr(tuple(values.values())), values)
        return QueryResult(seen.values())

    def frequency(self, fields: str | list[str]) -> list[dict]:
        """How often each combination of ``fields`` occurs, most frequent first.

        Returns:
            List of dicts with the field values and ``count``
        """
        names = _as_tuple(fields)
        counts: Counter[tuple[Any, ...]] = Counter()
        for row in self._rows():
            if isinstance(row, dict):
                counts[tuple(_hashable(row.get(name)) for name in names)] += 1
        return QueryResult(
            {**dict(zip(names, values, strict=True)), "count": count}
            for values, count in counts.most_common()
        )

    def validate(self, rules: str | list[dict[str, Any]]) -> dict[str, Any]:
        """Check every record against validation rules.

        Args:
            rules: Rules file (YAML/JSON, see ``undatum validate``) or a list of rule dicts

        Returns:
            ``{"records": n, "valid": n_valid, "violations": [...]}``
        """
        from ..common.validation_rules import (
            ValidationRule,
            ValidationRuleSet,
            parse_validation_rules,
        )

        if isinstance(rules, str):
            rule_set = parse_validation_rules(rules)
        else:
            rule_set = ValidationRuleSet([ValidationRule(rule) for rule in rules])
        violations: list[dict[str, Any]] = []
        records = valid = 0
        for index, row in enumerate(self._rows()):
            records += 1
            found = rule_set.validate_record(row, index) if isinstance(row, dict) else []
            violations.extend(found)
            valid += not found
        return {"records": records, "valid": valid, "violations": violations}

    def schema(self, limit: int = 1000) -> dict[str, Any]:
        """Infer a schema (field types, nested structure) from the first ``limit`` records.

        Returns:
            Schema dict as produced by ``undatum schema``
        """
        from ..common.scheme import get_schema, merge_schemes

        sample = [r for r in itertools.islice(self._rows(), limit) if isinstance(r, dict)]
        return cast(dict[str, Any], merge_schemes([get_schema(r) for r in sample]) or {})

    def quality(
        self,
        rules: str | None = None,
        schema: str | None = None,
        thresholds: str | None = None,
    ) -> dict[str, Any]:
        """Data quality report: field profiles, schema differences, rule violations, verdict.

        Args:
            rules: Validation rule file (YAML/JSON).
            schema: Expected schema (``undatum schema --json`` output, JSON Schema,
                Frictionless schema, or a data file).
            thresholds: Thresholds file; ``report["verdict"]["passed"]`` is ``False`` when
                one fails.

        Returns:
            The ``undatum.quality/1`` report (without the ``schema`` id key).

        Example:
            >>> Dataset.read("data.csv").quality()["summary"]["rows"]
            1000
        """
        from ..cmds.quality import build_report

        with self._materialized() as path:
            return build_report(
                path, rules=rules, schema=schema, thresholds=thresholds, options=self._spec.options
            )

    def stats(self, **options: Any) -> dict[str, Any]:
        """Statistics profile (types, uniqueness, lengths, distributions).

        Args:
            **options: ``checkdates``, ``engine``, ``flatten_nested``, ...

        Returns:
            Profile with ``count``, ``num_fields``, ``fieldtypes``, ``fields``, ``dictkeys``
            and per-field details under ``debug``

        Example:
            >>> Dataset.read("data.csv").stats()["count"]
            1000
        """
        from ..cmds.statistics import StatProcessor

        with self._materialized() as path:
            stats_opts = {**self._spec.options, "quiet": True, "progress": False, **options}
            profile = StatProcessor().stats(path, stats_opts)
        return StatsResult(profile or {})

    def package(
        self,
        output: str | None = None,
        package_dir: str | None = None,
        **options: Any,
    ) -> dict[str, Any]:
        """Generate a Frictionless Data Package descriptor for this dataset.

        Args:
            output: Output ``datapackage.json`` path
            package_dir: Optional directory to materialize the package
            **options: Packaging options (autodoc, metadata, ...)

        Returns:
            Dictionary with ``package``, ``output_file`` and optional ``archive_path``
        """
        from ..cmds.packager import Packager

        pack_opts = {**self._spec.options, "quiet": True, **options}
        if output:
            pack_opts["output"] = output
        if package_dir:
            pack_opts["package_dir"] = package_dir
        with self._materialized() as path:
            return Packager().create([path], pack_opts)

    def _materialized(self) -> _Materialized:
        """A file holding the plan's records (the source itself when there are no steps)."""
        return _Materialized(self)

    @classmethod
    def convert_many(
        cls,
        source: str,
        dest: str,
        *,
        to_ext: str | None = None,
        filename_pattern: str | None = None,
        **options: Any,
    ) -> Any:
        """Bulk-convert a directory or glob of files.

        Same as ``undatum convert --recursive``; ``to_ext`` is required unless
        ``format_out`` is set.

        Args:
            source: Directory path or glob pattern
            dest: Output directory
            to_ext: Target extension (e.g. ``"jsonl"``)
            filename_pattern: Output name pattern with ``{name}``, ``{stem}`` and ``{ext}``
            **options: Conversion options (encoding, quotechar, profile, level, ...)

        Returns:
            iterabledata ``BulkConversionResult``

        Example:
            >>> Dataset.convert_many("./raw", "./out", to_ext="jsonl")
        """
        from ..cmds.converter import Converter

        opts = dict(options)
        if filename_pattern:
            opts["filename_pattern"] = filename_pattern
        return Converter().bulk_convert(source, dest, opts, to_ext=to_ext)

    # ------------------------------------------------------------------ interop

    def to_pandas(self, chunksize: int | None = None) -> Any:
        """Convert to a pandas DataFrame (or an iterator of them with ``chunksize``)."""
        from iterable.dataframe_adapters import iterable_to_pandas

        return iterable_to_pandas(iter(self), chunksize=chunksize)

    def to_polars(self, chunksize: int | None = None) -> Any:
        """Convert to a Polars DataFrame (needs ``undatum[polars]``)."""
        from iterable.dataframe_adapters import iterable_to_polars

        return iterable_to_polars(iter(self), chunksize=chunksize)

    def to_dask(self, chunksize: int = 1000000) -> Any:
        """Convert to a Dask DataFrame (needs ``undatum[dask]``)."""
        from iterable.dataframe_adapters import iterable_to_dask

        return iterable_to_dask(iter(self), chunksize=chunksize)

    def as_dataclasses(self, dataclass_type: type, skip_empty: bool = True) -> Iterator[Any]:
        """Iterate records as instances of a dataclass.

        Args:
            dataclass_type: The dataclass to build
            skip_empty: Skip empty records

        Yields:
            Instances of ``dataclass_type``
        """
        from iterable.helpers.typed import as_dataclasses

        return as_dataclasses(cast(Any, self), dataclass_type, skip_empty=skip_empty)

    def as_pydantic(
        self, model_type: type, skip_empty: bool = True, validate: bool = True
    ) -> Iterator[Any]:
        """Iterate records as pydantic models (needs pydantic).

        Args:
            model_type: The model class
            skip_empty: Skip empty records
            validate: Validate fields

        Yields:
            Instances of ``model_type``
        """
        from iterable.helpers.typed import as_pydantic

        return as_pydantic(cast(Any, self), model_type, skip_empty=skip_empty, validate=validate)


def _hashable(value: Any) -> Any:
    try:
        hash(value)
        return value
    except TypeError:
        return repr(value)


class _Materialized:
    """Context manager: a path with the plan's records, removed afterwards if temporary."""

    def __init__(self, dataset: Dataset):
        self._dataset = dataset
        self._temp: str | None = None

    def __enter__(self) -> str:
        spec = self._dataset._spec
        if not self._dataset._steps and spec.path is not None:
            return spec.path
        fd, self._temp = tempfile.mkstemp(prefix="undatum-sdk-", suffix=".jsonl")
        os.close(fd)
        write_rows(self._dataset._rows(), self._temp, format_out="jsonl")
        return self._temp

    def __exit__(self, *exc: object) -> None:
        if self._temp and os.path.exists(self._temp):
            os.remove(self._temp)
