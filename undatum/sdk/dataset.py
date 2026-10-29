"""Fluent, lazy ``Dataset`` API over the operation registry.

A ``Dataset`` is an immutable plan: a source plus a tuple of operation calls. Transform
methods return a new ``Dataset`` with one more step and read nothing. The plan runs when
results are needed — iteration, :meth:`Dataset.write`, :meth:`Dataset.count`,
:meth:`Dataset.stats`, DataFrame export — and records stream from step to step as Python
objects (no intermediate files, types preserved).

When the source is DuckDB-readable (natively or through Arrow) and every step has a DuckDB
form, :meth:`Dataset.write`, :meth:`Dataset.count`, :meth:`Dataset.head`,
:meth:`Dataset.uniq`, :meth:`Dataset.frequency`, :meth:`Dataset.schema` and the Arrow and
DataFrame exports run the plan as one DuckDB query, with the results of the Python engine.
``Dataset.read(path, engine="python")`` turns this off.
"""

from __future__ import annotations

import itertools
import logging
import os
import re
import tempfile
from collections import Counter, deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, TypeVar, cast

from ..common.engine_selector import validate_engine
from ..common.errors import DependencyError, UndatumError
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
    compose_sql,
    get_operation,
    write_query,
    write_rows,
)
from ..ops.base import quote
from .results import QueryResult, StatsResult

if TYPE_CHECKING:
    from ..common.duckdb_config import Workload

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Rows per Arrow batch read from DuckDB or built from records.
BATCH_ROWS = 10_000


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

    def _sql(
        self,
        fetch: Callable[[Any, str], T | None],
        extra: dict | None = None,
        *,
        matches: str | None = "values",
        workload: Workload = "row",
        keep_open: bool = False,
        columns: list[str] | None = None,
    ) -> T | None:
        """Run the plan as one DuckDB query: ``fetch(conn, query)``, or ``None`` to use Python.

        DuckDB runs the plan when the source is DuckDB-readable (natively or through Arrow),
        every step has a SQL form and the ``engine`` option is not ``python``; steps whose SQL
        form holds every record (``dedup``, ``reverse``) need ``engine="duckdb"``, as in the
        CLI. ``fetch`` may return ``None`` to use Python as well.

        Args:
            fetch: Runs the query on the connection and returns the result.
            extra: Reader options for this call.
            matches: What the result shares with the Python engine: ``"values"`` (the
                records, value for value), ``"rows"`` (which records) or ``None`` (the text a
                writer makes of them, as in the CLI).
            workload: DuckDB workload (see ``WORKLOAD_DEFAULTS``).
            keep_open: ``fetch`` returns a generator that closes the connection.
            columns: The only columns ``fetch`` uses, when the plan has no steps (an Arrow
                reader then reads only them).
        """
        options = {**self._spec.options, **(extra or {})}
        engine = validate_engine(options.get("engine"))
        if self._spec.path is None or engine == "python":
            return None
        steps = [(get_operation(call.name), call.config) for call in self._steps]
        holds_all_rows = any(op.sql_holds_all_rows for op, _ in steps)
        if holds_all_rows and engine != "duckdb":
            return None  # the Python forms keep memory bounded
        source = RowSource(self._spec.path, options)
        if not source.duckdb_readable():
            return None
        try:
            import duckdb

            from ..common.duckdb_config import duckdb_connection

            conn = duckdb_connection(options, "ordered" if holds_all_rows else workload)
        except Exception:  # pragma: no cover - DuckDB missing or misconfigured
            return None
        handed_over = False
        try:
            relation = source.duckdb_relation(conn, None if steps else columns)
            if relation is not None and matches is not None:
                relation = _python_relation(conn, relation, source, matches)
            query = compose_sql(conn, relation, steps) if relation is not None else None
            if query is None:
                return None
            logger.debug("Dataset: DuckDB plan: %s", query)
            result = fetch(conn, query)
            handed_over = keep_open and result is not None
            return result
        except (duckdb.Error, ValueError) as exc:
            logger.warning("DuckDB plan failed, using the Python engine: %s", exc)
            return None
        finally:
            if not handed_over:
                conn.close()

    def _sql_table(self) -> Any | None:
        """The plan's records as one ``pyarrow.Table`` read by DuckDB, or ``None``."""
        return self._sql(lambda conn, query: conn.sql(query).to_arrow_reader(BATCH_ROWS).read_all())

    def _chunks(self, size: int, *, strict: bool) -> Iterator[Any]:
        """The plan's records as ``pyarrow.Table`` chunks of ``size`` rows.

        With ``strict=False`` a chunk of records that Arrow cannot hold (a field mixing value
        types) is yielded as the list of records instead.
        """
        stream = self._sql(lambda conn, query: _arrow_stream(conn, query, size), keep_open=True)
        if stream is not None:
            return stream
        return _record_chunks(self._rows(), size, strict=strict)

    def _frame(
        self,
        from_table: Callable[[Any], Any],
        from_records: Callable[[list[dict[str, Any]]], Any],
        concat: Callable[[list[Any]], Any],
        empty: Callable[[], Any],
    ) -> Any:
        """One DataFrame of the plan's records, built from Arrow where Arrow holds them."""
        table = self._sql_table()
        if table is not None:
            return from_table(table)
        chunks = list(_record_chunks(self._rows(), BATCH_ROWS, strict=False))
        if not chunks:
            return empty()
        if not any(isinstance(chunk, list) for chunk in chunks):
            try:
                return from_table(_concat_tables(chunks))
            except UndatumError:
                pass  # a field has one type in some chunks and another in others
        frames = [from_records(c) if isinstance(c, list) else from_table(c) for c in chunks]
        return concat(frames)

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
        written = self._sql(
            lambda conn, query: write_query(conn, query, path, format_out), matches=None
        )
        if written is None:
            write_rows(self._rows(), path, format_out=format_out)

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
        if not self._steps and self._spec.path is not None:
            from ..cmds.counter import count_records

            return count_records(self._spec.path, {**self._spec.options, **options})
        counted = self._sql(_count, options or None, matches="rows", workload="aggregate")
        if counted is not None:
            return counted
        return sum(1 for _ in self._rows(options or None))

    def head(self, n: int = 10, **options: Any) -> list[dict]:
        """First ``n`` records.

        Args:
            n: Number of records
            **options: Reader options applied for this call

        Returns:
            List of records
        """
        if n >= 0:
            records = self._sql(lambda conn, query: _first(conn, query, n), options or None)
            if records is not None:
                return QueryResult(records)
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
        groups = self._sql(
            lambda conn, query: _groups(conn, query, names), workload="ordered", columns=list(names)
        )
        if groups is not None:
            return QueryResult(dict(zip(names, values, strict=True)) for values in groups)
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
        groups = self._sql(
            lambda conn, query: _groups(conn, query, names, counts=True),
            workload="ordered",
            columns=list(names),
        )
        if groups is not None:
            found = [(values[:-1], values[-1]) for values in groups]
        else:
            counts: Counter[tuple[Any, ...]] = Counter()
            for row in self._rows():
                if isinstance(row, dict):
                    counts[tuple(_hashable(row.get(name)) for name in names)] += 1
            found = counts.most_common()
        return QueryResult(
            {**dict(zip(names, values, strict=True)), "count": count} for values, count in found
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

        sample = self._sql(lambda conn, query: _first(conn, query, limit)) if limit >= 0 else None
        if sample is None:
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

        with self._materialized() as (path, reader_options):
            return build_report(
                path, rules=rules, schema=schema, thresholds=thresholds, options=reader_options
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

        with self._materialized() as (path, reader_options):
            stats_opts = {**reader_options, "quiet": True, "progress": False, **options}
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

        with self._materialized() as (path, reader_options):
            pack_opts = {**reader_options, "quiet": True, **options}
            if output:
                pack_opts["output"] = output
            if package_dir:
                pack_opts["package_dir"] = package_dir
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

    def to_arrow(self, chunksize: int | None = None) -> Any:
        """Convert to a ``pyarrow.Table`` (or an iterator of tables with ``chunksize``).

        A plan DuckDB runs (see the module notes) is read by DuckDB straight into Arrow; other
        plans convert their records in batches. CSV fields stay text, as in the Python reader.

        Args:
            chunksize: Rows per table; ``None`` returns one table.

        Returns:
            ``pyarrow.Table``, or an iterator of tables of ``chunksize`` rows (the last may
            be shorter)

        Raises:
            UndatumError: A field has values Arrow cannot hold in one column (numbers and
                text, for example); :meth:`to_pandas` accepts them.

        Example:
            >>> Dataset.read("data.parquet").select(["id", "name"]).to_arrow().num_rows
            1000
        """
        if chunksize:
            return self._chunks(chunksize, strict=True)
        table = self._sql_table()
        if table is not None:
            return table
        return _concat_tables(list(_record_chunks(self._rows(), BATCH_ROWS, strict=True)))

    def to_pandas(self, chunksize: int | None = None) -> Any:
        """Convert to a pandas DataFrame (or an iterator of them with ``chunksize``).

        The frames are built from Arrow (see :meth:`to_arrow`); records whose fields mix
        value types that Arrow cannot hold in one column become frames of Python objects.

        Args:
            chunksize: Rows per frame; ``None`` returns one frame.

        Returns:
            ``pandas.DataFrame``, or an iterator of frames of ``chunksize`` rows

        Raises:
            DependencyError: pandas is not installed (``pip install "undatum[pandas]"``).
        """
        from ..io.arrow import import_pandas

        pd = import_pandas("Dataset.to_pandas()")

        def frame(chunk: Any) -> Any:
            return pd.DataFrame(chunk) if isinstance(chunk, list) else chunk.to_pandas()

        if chunksize:
            return (frame(chunk) for chunk in self._chunks(chunksize, strict=False))
        return self._frame(
            lambda table: table.to_pandas(),
            pd.DataFrame,
            lambda frames: pd.concat(frames, ignore_index=True),
            pd.DataFrame,
        )

    def to_polars(self, chunksize: int | None = None) -> Any:
        """Convert to a Polars DataFrame (or an iterator of them with ``chunksize``).

        Needs ``undatum[polars]``. The frames are built from Arrow, as in :meth:`to_pandas`.

        Args:
            chunksize: Rows per frame; ``None`` returns one frame.

        Returns:
            ``polars.DataFrame``, or an iterator of frames of ``chunksize`` rows
        """
        try:
            import polars as pl
        except ImportError:
            raise DependencyError(
                "polars",
                feature="Dataset.to_polars()",
                install_command='pip install "undatum[polars]"',
            ) from None

        def frame(chunk: Any) -> Any:
            return pl.DataFrame(chunk) if isinstance(chunk, list) else pl.from_arrow(chunk)

        if chunksize:
            return (frame(chunk) for chunk in self._chunks(chunksize, strict=False))
        return self._frame(
            pl.from_arrow,
            pl.DataFrame,
            lambda frames: pl.concat(frames, how="diagonal_relaxed"),
            pl.DataFrame,
        )

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


# Words of the DuckDB types whose Python values equal those of the Python readers of Parquet,
# ORC and Arrow files (checked type by type in tests/test_sdk_sql.py). Others come back as other
# values: nanosecond and zoned timestamps, maps (dicts, not lists of pairs), UUIDs, intervals.
_SAME_VALUE_TYPES = frozenset(
    {
        "BOOLEAN",
        "TINYINT",
        "SMALLINT",
        "INTEGER",
        "BIGINT",
        "UTINYINT",
        "USMALLINT",
        "UINTEGER",
        "UBIGINT",
        "FLOAT",
        "DOUBLE",
        "DECIMAL",
        "VARCHAR",
        "BLOB",
        "DATE",
        "TIME",
        "TIMESTAMP",
        "TIMESTAMP_MS",
        "STRUCT",
        "NULL",
    }
)
_TYPE_WORD = re.compile(r"\b[A-Z][A-Z0-9_]*\b")


def _python_relation(conn: Any, relation: str, source: RowSource, matches: str) -> str | None:
    """``relation`` with the records the Python reader gives, or ``None`` when DuckDB's differ.

    CSV is text in both readers, but DuckDB reads empty fields as NULL (the Python reader
    gives ``''``) and can take other names from the header (a byte-order mark, repeated or
    padded names, a first line it does not take for a header). DuckDB types JSON values
    (dates in strings, integers and floats in one column), so JSON serves only
    ``matches="rows"``. Typed formats match unless a column has a type whose Python values
    differ, or (Parquet) an Arrow duration that DuckDB reads as integers.
    """
    fmt = source.format_id
    if fmt not in ("csv", "tsv"):
        if matches == "rows":
            return relation
        if fmt not in ("parquet", "orc", "arrow"):
            return None
    described = conn.sql(f"DESCRIBE SELECT * FROM {relation}").fetchall()
    if fmt in ("csv", "tsv"):
        names = [str(row[0]) for row in described]
        if names != source.csv_header():
            return None
        columns = ", ".join(f"COALESCE({quote(name)}, '') AS {quote(name)}" for name in names)
        return f"(SELECT {columns} FROM {relation})"
    if any(not set(_TYPE_WORD.findall(str(row[1]))) <= _SAME_VALUE_TYPES for row in described):
        return None
    if fmt == "parquet" and _has_durations(source.path):
        return None
    return relation


def _has_durations(path: str) -> bool:
    import pyarrow as pa
    import pyarrow.parquet as pq

    def has(kind: Any) -> bool:
        return bool(
            pa.types.is_duration(kind)
            or any(has(kind.field(i).type) for i in range(kind.num_fields))
        )

    return any(has(item.type) for item in pq.read_schema(path))


def _count(conn: Any, query: str) -> int:
    row = conn.execute(f"SELECT count(*) FROM ({query})").fetchone()
    return int(row[0]) if row else 0


def _first(conn: Any, query: str, n: int) -> list[dict[str, Any]]:
    """The first ``n`` records of ``query``."""
    result = conn.execute(f"SELECT * FROM ({query}) LIMIT {int(n)}")
    names = [column[0] for column in result.description]
    return [dict(zip(names, values, strict=True)) for values in result.fetchall()]


def _groups(
    conn: Any, query: str, names: tuple[str, ...], *, counts: bool = False
) -> list[tuple[Any, ...]] | None:
    """Distinct values of ``names``, in first-seen order.

    With ``counts`` each group ends with its count, most frequent first (ties in first-seen
    order). ``None`` when Python compares the values otherwise.
    """
    types = {str(row[0]): str(row[1]) for row in conn.sql(f"DESCRIBE {query}").fetchall()}
    # A missing field is None in every Python record; nested values are compared by repr().
    if not names or any(
        name not in types or "[" in types[name] or types[name].startswith(("STRUCT", "MAP"))
        for name in names
    ):
        return None
    keys = ", ".join(quote(name) for name in names)
    numbered = f"SELECT {keys}, row_number() OVER () AS __undatum_row FROM ({query})"
    if counts:
        sql = (
            f"SELECT {keys}, count(*) AS __undatum_count FROM ({numbered}) GROUP BY {keys} "
            "ORDER BY __undatum_count DESC, min(__undatum_row)"
        )
    else:
        sql = f"SELECT {keys} FROM ({numbered}) GROUP BY {keys} ORDER BY min(__undatum_row)"
    return list(conn.execute(sql).fetchall())


def _arrow_stream(conn: Any, query: str, size: int) -> Iterator[Any]:
    """Tables of ``size`` rows from ``query``; the generator closes ``conn``.

    The first batch is read here, so a query that fails at once leaves the Python engine.
    """
    import duckdb

    batches = iter(conn.sql(query).to_arrow_reader(size))
    first = next(batches, None)

    def tables() -> Iterator[Any]:
        try:
            if first is not None:
                yield from _rebatch(itertools.chain([first], batches), size)
        except duckdb.Error as exc:
            raise UndatumError(
                f"DuckDB could not read the input: {exc}\n"
                'Read it with Dataset.read(path, engine="python").'
            ) from exc
        finally:
            conn.close()

    return tables()


def _rebatch(batches: Iterable[Any], size: int) -> Iterator[Any]:
    """Tables of ``size`` rows (the last may be shorter) from record batches of any size."""
    import pyarrow as pa

    pending: list[Any] = []
    rows = 0
    for batch in batches:
        pending.append(batch)
        rows += batch.num_rows
        while rows >= size:
            table = pa.Table.from_batches(pending)
            yield table.slice(0, size)
            rest = table.slice(size)
            pending, rows = rest.to_batches(), rest.num_rows
    if rows:
        yield pa.Table.from_batches(pending)


def _record_chunks(rows: Iterator[Any], size: int, *, strict: bool) -> Iterator[Any]:
    """``pyarrow.Table`` chunks of ``size`` records (dicts; other rows are skipped).

    A chunk Arrow cannot hold raises with ``strict``, else it is yielded as the list of
    records.
    """
    records = (row for row in rows if isinstance(row, dict))
    while batch := list(itertools.islice(records, size)):
        try:
            yield _records_table(batch)
        except UndatumError:
            if strict:
                raise
            yield batch


def _records_table(batch: list[dict[str, Any]]) -> Any:
    from ..io.arrow import records_table

    return records_table(batch)


def _concat_tables(tables: list[Any]) -> Any:
    """One table from chunks whose types may differ (integers and floats, missing fields)."""
    import pyarrow as pa

    if not tables:
        return pa.table({})
    try:
        return pa.concat_tables(tables, promote_options="permissive")
    except (pa.ArrowInvalid, pa.ArrowTypeError) as exc:
        raise UndatumError(f"Fields change type between records: {exc}") from exc


class _Materialized:
    """Context manager: a path with the plan's records, removed afterwards if temporary."""

    def __init__(self, dataset: Dataset):
        self._dataset = dataset
        self._temp: str | None = None

    def __enter__(self) -> tuple[str, dict[str, Any]]:
        spec = self._dataset._spec
        if not self._dataset._steps and spec.path is not None:
            return spec.path, dict(spec.options)
        fd, self._temp = tempfile.mkstemp(prefix="undatum-sdk-", suffix=".jsonl")
        os.close(fd)
        try:
            write_rows(self._dataset._rows(), self._temp, format_out="jsonl")
        except BaseException:
            self.__exit__()
            raise
        # The source's format, encoding, sheet and flattening settings have
        # already been applied. This file contains the resulting JSONL records.
        return self._temp, {"format_in": "jsonl"}

    def __exit__(self, *exc: object) -> None:
        if self._temp and os.path.exists(self._temp):
            os.remove(self._temp)
