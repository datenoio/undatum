"""Preserving native Parquet and ORC rewrite and independent value verification."""

from __future__ import annotations

import base64
import hashlib
import inspect
import struct
import time
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from .errors import DependencyError, ValidationError
from .file_snapshot import FileSnapshot
from .repack_types import RepackBudget, RepackError, RepackOptions, RepackPlan


def arrow_values_equal(left: Any, right: Any) -> bool:
    """Compare visible Arrow values, including floating-point bits inside nested arrays."""
    import pyarrow as pa
    import pyarrow.compute as pc

    if left.type != right.type or len(left) != len(right):
        return False
    dtype = left.type
    if pa.types.is_floating(dtype):
        integer = {16: pa.int16(), 32: pa.int32(), 64: pa.int64()}[dtype.bit_width]
        return bool(left.view(integer).equals(right.view(integer)))
    if pa.types.is_dictionary(dtype):
        return arrow_values_equal(left.dictionary_decode(), right.dictionary_decode())
    if pa.types.is_struct(dtype):
        if not left.is_null().equals(right.is_null()):
            return False
        visible = pc.invert(left.is_null())
        return all(
            arrow_values_equal(
                pc.filter(left.field(i), visible), pc.filter(right.field(i), visible)
            )
            for i in range(dtype.num_fields)
        )
    if (
        pa.types.is_list(dtype)
        or pa.types.is_large_list(dtype)
        or pa.types.is_fixed_size_list(dtype)
        or pa.types.is_map(dtype)
    ):
        return all(
            a.is_valid == b.is_valid and (not a.is_valid or arrow_values_equal(a.values, b.values))
            for a, b in zip(left, right, strict=True)
        )
    return bool(left.equals(right))


def _batches(source: Any, options: RepackOptions) -> Iterator[Any]:
    for group in range(source.metadata.num_row_groups):
        yield from source.iter_batches(
            batch_size=options.batch_size, row_groups=[group], use_threads=False
        )


def _verify_parquet(source: Any, output: Any, options: RepackOptions, budget: RepackBudget) -> None:
    if not source.schema.equals(output.schema):
        raise RepackError("Candidate changed the physical Parquet schema or field identifiers.")
    if not source.schema_arrow.equals(output.schema_arrow, check_metadata=True):
        raise RepackError("Candidate changed the logical Parquet schema/metadata.")
    expected, actual = dict(source.metadata.metadata or {}), dict(output.metadata.metadata or {})
    if b"ARROW:schema" not in expected:
        actual.pop(b"ARROW:schema", None)
    if expected != actual:
        raise RepackError("Candidate changed Parquet file metadata.")
    original, candidate = iter(_batches(source, options)), iter(_batches(output, options))
    left, right = next(original, None), next(candidate, None)
    while left is not None and right is not None:
        count = min(left.num_rows, right.num_rows)
        a, b = left.slice(0, count), right.slice(0, count)
        budget.check(a.nbytes + b.nbytes)
        if any(not arrow_values_equal(a.column(i), b.column(i)) for i in range(a.num_columns)):
            raise RepackError("Candidate changed Parquet values or row order.")
        left = next(original, None) if count == left.num_rows else left.slice(count)
        right = next(candidate, None) if count == right.num_rows else right.slice(count)
    if left is not None or right is not None:
        raise RepackError("Candidate changed Parquet row count.")


def repack_parquet(
    plan: RepackPlan, target: str, options: RepackOptions, budget: RepackBudget
) -> dict[str, Any]:
    """Rewrite original schema, metadata and compatible physical types, including empty files."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise DependencyError(
            "pyarrow", feature="Parquet repack", install_command='pip install "undatum[repack]"'
        ) from exc

    started = time.monotonic()
    rows, decoded = 0, 0
    with pq.ParquetFile(plan.source, pre_buffer=False, memory_map=False) as source:
        writer_schema = source.schema_arrow
        original_schema = (source.metadata.metadata or {}).get(b"ARROW:schema")
        if original_schema:
            # Arrow 16 normalizes LIST child names on read. Reusing its normalized
            # schema changes serialized schema metadata even when values agree.
            writer_schema = pa.ipc.read_schema(pa.BufferReader(base64.b64decode(original_schema)))
        settings: dict[str, Any] = {
            "compression": plan.target_codec,
            "version": source.metadata.format_version,
            "store_schema": True,
            "use_compliant_nested_type": any(
                ".list.element" in source.schema.column(i).path for i in range(len(source.schema))
            ),
        }
        if plan.level is not None:
            settings["compression_level"] = plan.level
        physical = [source.schema.column(i).physical_type for i in range(len(source.schema))]
        if "INT96" in physical:
            settings["use_deprecated_int96_timestamps"] = True
        integer_decimals = any(
            "Decimal" in str(source.schema.column(i).logical_type)
            and physical[i] in {"INT32", "INT64"}
            for i in range(len(physical))
        )
        if integer_decimals:
            if "store_decimal_as_integer" not in inspect.signature(pq.ParquetWriter).parameters:
                raise ValidationError(
                    "This PyArrow version cannot preserve integer decimals.", field="input"
                )
            settings["store_decimal_as_integer"] = True
        sorting: set[tuple[Any, ...]] = set()
        for group in range(source.metadata.num_row_groups):
            metadata = source.metadata.row_group(group)
            sorting.add(tuple(getattr(metadata, "sorting_columns", ())))
            for column in range(metadata.num_columns):
                if metadata.column(column).file_path:
                    raise ValidationError(
                        "External Parquet column chunks are unsupported.", field="input"
                    )
        if len(sorting) > 1:
            raise ValidationError(
                "Mixed Parquet sorting declarations cannot be preserved.", field="input"
            )
        declared = next(iter(sorting), ())
        if declared:
            if "sorting_columns" not in inspect.signature(pq.ParquetWriter).parameters:
                raise ValidationError(
                    "This PyArrow version cannot preserve sorting declarations.", field="input"
                )
            settings["sorting_columns"] = list(declared)
        # Initializing from schema, even before any batch, is essential for zero rows.
        with pq.ParquetWriter(target, writer_schema, **settings) as writer:
            pending: list[Any] = []
            pending_rows = 0
            for batch in _batches(source, options):
                budget.check(batch.nbytes)
                decoded += batch.nbytes
                rows += batch.num_rows
                while batch.num_rows:
                    count = min(batch.num_rows, options.row_group_size - pending_rows)
                    pending.append(batch.slice(0, count))
                    pending_rows += count
                    batch = batch.slice(count)
                    if pending_rows == options.row_group_size:
                        writer.write_table(
                            pa.Table.from_batches(pending).cast(writer_schema),
                            row_group_size=pending_rows,
                        )
                        pending, pending_rows = [], 0
                        budget.check()
            if pending:
                writer.write_table(
                    pa.Table.from_batches(pending).cast(writer_schema),
                    row_group_size=pending_rows,
                )
            # PyArrow 16 supports metadata on the schema but not all later writer APIs.
            if hasattr(writer, "add_key_value_metadata"):
                writer.add_key_value_metadata(source.metadata.metadata or {})
        budget.check()
        encode_seconds = time.monotonic() - started
        verified = time.monotonic()
        snapshot = FileSnapshot.capture(target, budget.check)
        with pq.ParquetFile(target, pre_buffer=False, memory_map=False) as output:
            _verify_parquet(source, output, options, budget)
            if any(
                tuple(getattr(output.metadata.row_group(i), "sorting_columns", ())) != declared
                for i in range(output.metadata.num_row_groups)
            ):
                raise RepackError("Candidate changed Parquet sorting declarations.")
        snapshot.require_unchanged(check=budget.check)
    return {
        "rows": rows,
        "decoded_bytes": decoded,
        "verification": {
            "method": "parquet-schema-metadata-values",
            "passed": True,
            "candidate_sha256": snapshot.digest,
        },
        "timings": {
            "encode_seconds": encode_seconds,
            "verify_seconds": time.monotonic() - verified,
        },
    }


def _value_hash(value: Any, digest: Any) -> None:
    """Hash typed native values without rounding floats, decimals or timestamps."""
    if value is None:
        digest.update(b"N")
    elif isinstance(value, bool):
        digest.update(b"T" if value else b"F")
    elif isinstance(value, float):
        digest.update(b"D" + struct.pack(">d", value))
    elif isinstance(value, dict):
        pairs = []
        for key, item in value.items():
            entry = hashlib.sha256()
            _value_hash(key, entry)
            _value_hash(item, entry)
            pairs.append(entry.digest())
        digest.update(b"M" + struct.pack("<Q", len(pairs)))
        for pair in sorted(pairs):
            digest.update(pair)
    elif isinstance(value, (tuple, list)):
        digest.update(b"L" + struct.pack("<Q", len(value)))
        for item in value:
            _value_hash(item, digest)
    else:
        if isinstance(value, bytes):
            kind, raw = b"B", value
        elif isinstance(value, str):
            kind, raw = b"S", value.encode("utf8")
        elif isinstance(value, int):
            kind, raw = b"I", str(value).encode("ascii")
        elif isinstance(value, Decimal):
            kind, raw = b"C", str(value.as_tuple()).encode("ascii")
        elif isinstance(value, (date, datetime)):
            kind, raw = b"A", value.isoformat().encode("ascii")
        else:
            raise RepackError(f"Unsupported native value type: {type(value).__name__}")
        digest.update(kind + struct.pack("<Q", len(raw)) + raw)


def _orc_attributes(schema: Any) -> Any:
    """Retain type attributes and reject unions whose branch identity pyorc discards."""
    import pyorc

    if schema.kind == pyorc.TypeKind.UNION:
        raise ValidationError("ORC union branch preservation is unsupported.", field="input")
    children: list[Any] = []
    if schema.kind == pyorc.TypeKind.STRUCT:
        children = list(schema.fields.values())
    elif schema.kind == pyorc.TypeKind.LIST:
        children = [schema.type]
    elif schema.kind == pyorc.TypeKind.MAP:
        children = [schema.key, schema.value]
    return (str(schema), dict(schema.attributes), [_orc_attributes(child) for child in children])


class _TypedDigest:
    def __init__(self) -> None:
        self.hash = hashlib.sha256()
        self.bytes = 0

    def update(self, value: bytes) -> None:
        self.hash.update(value)
        self.bytes += len(value)

    def digest(self) -> bytes:
        return self.hash.digest()

    def hexdigest(self) -> str:
        return self.hash.hexdigest()


def repack_orc(
    plan: RepackPlan, target: str, options: RepackOptions, budget: RepackBudget
) -> dict[str, Any]:
    """Repack typed ORC rows and metadata with exact nanosecond timestamp converters."""
    try:
        import pyorc
        from pyorc.converters import ORCConverter
    except ImportError as exc:
        raise DependencyError(
            "pyorc", feature="ORC repack", install_command='pip install "undatum[repack]"'
        ) from exc

    class ExactTimestamp(ORCConverter):
        @staticmethod
        def from_orc(seconds: int, nanoseconds: int, timezone: Any) -> tuple[int, int]:
            return seconds, nanoseconds

        @staticmethod
        def to_orc(obj: Any, timezone: Any) -> tuple[int, int]:
            return int(obj[0]), int(obj[1])

    converters: dict[pyorc.TypeKind, type[ORCConverter]] = {
        pyorc.TypeKind.TIMESTAMP: ExactTimestamp,
        pyorc.TypeKind.TIMESTAMP_INSTANT: ExactTimestamp,
    }
    kinds = {"none": 0, "zlib": 1, "snappy": 2, "lzo": 3, "lz4": 4, "zstd": 5}
    started = time.monotonic()
    expected, rows = _TypedDigest(), 0
    with open(plan.source, "rb") as raw:
        source = pyorc.Reader(raw, converters=converters)
        schema = source.schema
        attributes, metadata = _orc_attributes(source.schema), dict(source.user_metadata)
        if source.format_version != (0, 12):
            raise ValidationError(
                "Unsupported ORC format version for preserving rewrite.", field="input"
            )
        with open(target, "wb") as output:
            with pyorc.Writer(
                output,
                schema,
                converters=converters,
                compression=pyorc.CompressionKind(kinds[plan.target_codec]),
                compression_strategy=(
                    pyorc.CompressionStrategy.SPEED
                    if options.profile == "fast"
                    else pyorc.CompressionStrategy.COMPRESSION
                ),
                row_index_stride=source.row_index_stride,
                compression_block_size=source.compression_block_size,
            ) as writer:
                writer.set_user_metadata(**metadata)
                for row in source:
                    before = expected.bytes
                    _value_hash(row, expected)
                    budget.check(expected.bytes - before)
                    writer.write(row)
                    rows += 1
        budget.check()
    encode_seconds = time.monotonic() - started
    verified = time.monotonic()
    snapshot = FileSnapshot.capture(target, budget.check)
    actual, actual_rows = _TypedDigest(), 0
    with open(target, "rb") as raw:
        reader = pyorc.Reader(raw, converters=converters)
        if _orc_attributes(reader.schema) != attributes or reader.user_metadata != metadata:
            raise RepackError("Candidate changed ORC schema or metadata.")
        for row in reader:
            before = actual.bytes
            _value_hash(row, actual)
            budget.check(actual.bytes - before)
            actual_rows += 1
    if actual_rows != rows or actual.digest() != expected.digest():
        raise RepackError("Candidate changed ORC values, row count or order.")
    snapshot.require_unchanged(check=budget.check)
    return {
        "rows": rows,
        "decoded_bytes": expected.bytes,
        "verification": {
            "method": "orc-typed-sha256",
            "candidate_sha256": snapshot.digest,
            "passed": True,
            "sha256": actual.hexdigest(),
        },
        "timings": {
            "encode_seconds": encode_seconds,
            "verify_seconds": time.monotonic() - verified,
        },
    }
