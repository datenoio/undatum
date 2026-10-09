"""Utility functions for file operations and data processing.

This module provides helper functions for encoding detection, delimiter detection,
file type identification, dictionary manipulation, and data type guessing.
"""

from collections import OrderedDict
from typing import Any

from . import constants
from .constants import DEFAULT_OPTIONS


def detect_encoding(filename: str, limit: int = 1000000) -> dict[str, Any]:
    """Detect encoding of a file.

    Args:
        filename: Path to the file to analyze.
        limit: Maximum number of bytes to read for detection (default: 1000000).

    Returns:
        Dictionary with ``encoding``, ``confidence`` and ``language`` keys, as returned
        by iterabledata's encoding detection.
    """
    from iterable.helpers.utils import detect_encoding_raw

    return detect_encoding_raw(filename=filename, limit=limit)


def open_text_sample(filename: str, encoding: str = "utf8") -> Any:
    """Open a text file for reading, decompressing ``.gz``, ``.bz2``, ``.xz``, ``.zst``
    and ``.zip`` (first member) on the fly.

    Args:
        filename: Path to the file.
        encoding: Text encoding; undecodable bytes are replaced.

    Returns:
        A text stream (use it as a context manager).
    """
    import io

    lower = filename.lower()
    if lower.endswith(".gz"):
        import gzip

        return gzip.open(filename, "rt", encoding=encoding, errors="replace")
    if lower.endswith(".bz2"):
        import bz2

        return bz2.open(filename, "rt", encoding=encoding, errors="replace")
    if lower.endswith(".xz"):
        import lzma

        return lzma.open(filename, "rt", encoding=encoding, errors="replace")
    if lower.endswith((".zst", ".zstd")):
        import zstandard

        raw = zstandard.ZstdDecompressor().stream_reader(open(filename, "rb"), closefd=True)
        return io.TextIOWrapper(raw, encoding=encoding, errors="replace")
    if lower.endswith(".zip"):
        import zipfile

        archive = zipfile.ZipFile(filename)
        names = [n for n in archive.namelist() if not n.endswith("/")]
        if not names:
            archive.close()
            raise ValueError(f"{filename} is an empty ZIP archive")
        return io.TextIOWrapper(archive.open(names[0]), encoding=encoding, errors="replace")
    return open(filename, encoding=encoding, errors="replace")


def detect_delimiter(filename: str, encoding: str = "utf8", sample_lines: int = 20) -> str:
    """Detect delimiter used in a CSV-like file.

    Uses ``csv.Sniffer`` over a multi-line sample for quote-aware detection,
    falling back to first-line character counts when sniffing is inconclusive.

    Args:
        filename: Path to the CSV file to analyze.
        encoding: File encoding (default: 'utf8').
        sample_lines: Number of lines to sample for sniffing (default: 20).

    Returns:
        Most likely delimiter character (',', ';', '\\t', or '|').
    """
    import csv

    try:
        with open_text_sample(filename, encoding) as handle:
            sample_parts = []
            for _ in range(max(sample_lines, 1)):
                line = handle.readline()
                if not line:
                    break
                sample_parts.append(line)
            sample = "".join(sample_parts)
    except (OSError, EOFError, ValueError):
        return ","

    if not sample.strip():
        return ","

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        if dialect.delimiter in {",", ";", "\t", "|"}:
            return dialect.delimiter
    except csv.Error:
        pass

    # Fallback: first-line character counts
    first_line = sample.splitlines()[0] if sample else ""
    counts = {
        ",": first_line.count(","),
        ";": first_line.count(";"),
        "\t": first_line.count("\t"),
        "|": first_line.count("|"),
    }
    return max(counts, key=counts.get)


def get_file_type(filename: str) -> str | None:
    """Get file type based on extension.

    Args:
        filename: Path to the file.

    Returns:
        File extension if supported, None otherwise.
    """
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext in constants.SUPPORTED_FILE_TYPES:
        return ext
    return None


def get_option(options: dict[str, Any], name: str) -> Any:
    """Get option value from options dict, config defaults, or built-in defaults.

    Explicit ``None`` in ``options`` means "not set on the CLI" and falls through
    to ``undatum.yaml`` / environment defaults. Built-in ``DEFAULT_OPTIONS``
    apply only when the key is absent, so commands that pass ``delimiter=None``
    keep CSV auto-detection unless a config default is set.

    Args:
        options: Dictionary of user-provided options.
        name: Option name to retrieve.

    Returns:
        Option value if found, None otherwise.
    """
    value = _raw_option(options, name)
    if name == "engine" and value is not None:
        from .common.engine_selector import validate_engine

        return validate_engine(value)
    return value


def _raw_option(options: dict[str, Any], name: str) -> Any:
    if name in options and options[name] is not None:
        return options[name]
    from .common.app_config import get_cli_defaults

    cli_defaults = get_cli_defaults()
    if name in cli_defaults and cli_defaults[name] is not None:
        return cli_defaults[name]
    if name not in options and name in DEFAULT_OPTIONS:
        return DEFAULT_OPTIONS[name]
    return None


def get_dict_value(d: dict[str, Any] | list[dict[str, Any]] | None, keys: list[str]) -> list[Any]:
    """Get dictionary value by nested keys.

    Args:
        d: Dictionary or list of dictionaries to search.
        keys: List of nested keys to traverse.

    Returns:
        List of values found at the specified key path.
    """
    out = []
    if d is None:
        return out
    if len(keys) == 1:
        if isinstance(d, (dict, OrderedDict)):
            if keys[0] in d:
                out.append(d[keys[0]])
        else:
            for r in d:
                if r and keys[0] in r:
                    out.append(r[keys[0]])
    elif isinstance(d, (dict, OrderedDict)):
        if keys[0] in d:
            out.extend(get_dict_value(d[keys[0]], keys[1:]))
    else:
        for r in d:
            if keys[0] in r:
                out.extend(get_dict_value(r[keys[0]], keys[1:]))
    return out


def field_values(record: Any, field: str) -> list[Any]:
    """Return values for a field, preferring a literal key then a dotted path.

    After ``flatten_nested``, dotted names like ``city.lat`` are top-level keys.
    Without flattening, the same name is walked as nested ``city`` → ``lat``.
    """
    if not isinstance(record, dict) or not field:
        return []
    if field in record:
        return [record[field]]
    return get_dict_value(record, field.split("."))


def select_fields(record: dict[str, Any], fields: list[list[str]]) -> dict[str, Any]:
    """Select fields from a record without mutating the input.

    Args:
        record: Source dictionary.
        fields: List of field paths (nested keys as lists).

    Returns:
        New dictionary containing only the requested fields.
    """
    result: dict[str, Any] = {}
    for field_path in fields:
        if not field_path:
            continue
        values = get_dict_value(record, field_path)
        if not values:
            continue
        current = result
        for key in field_path[:-1]:
            nested = current.get(key)
            if not isinstance(nested, dict):
                nested = {}
                current[key] = nested
            current = nested
        value = values[0] if len(values) == 1 else values
        current[field_path[-1]] = value
    return result


def strip_dict_fields(
    record: dict[str, Any], fields: list[list[str]], startkey: int = 0
) -> dict[str, Any]:
    """Strip dictionary fields based on field list.

    Args:
        record: Dictionary to process.
        fields: List of field paths (nested keys as lists).
        startkey: Starting index for field path (default: 0).

    Returns:
        Modified dictionary with only specified fields retained.
    """
    # Create set for O(1) lookup instead of O(n) list lookup
    localf = set()
    for field in fields:
        if len(field) > startkey:
            localf.add(field[startkey])
    # Iterate over copy of keys to avoid modification during iteration
    keys = list(record.keys())
    for k in keys:
        if k not in localf:
            del record[k]

    for k, value in record.items():
        if isinstance(value, dict):
            record[k] = strip_dict_fields(value, fields, startkey + 1)
    return record


def dict_generator(indict: dict[str, Any] | Any, pre: list[str] | None = None):
    """Process dictionary and yield flattened key-value pairs.

    Recursively traverses nested dictionaries and lists, yielding
    key paths with their values. Skips '_id' keys.

    Args:
        indict: Input dictionary to process.
        pre: Prefix keys list for nested structures (default: None).

    Yields:
        Lists containing key path and value: [key1, key2, ..., value]
    """
    pre = pre[:] if pre else []
    if isinstance(indict, dict):
        for key, value in indict.items():  # Use dict.items() directly, no list() conversion
            if key == "_id":
                continue
            if isinstance(value, dict):
                yield from dict_generator(value, pre + [key])
            elif isinstance(value, (list, tuple)):
                for v in value:
                    if isinstance(v, dict):
                        yield from dict_generator(v, pre + [key])
            else:
                yield pre + [key, value]
    else:
        yield indict


def guess_int_size(i: int) -> str:
    """Guess appropriate integer size type based on value.

    Args:
        i: Integer value to analyze.

    Returns:
        String indicating size type: 'uint8', 'uint16', or 'uint32'.
    """
    if i < 255:
        return "uint8"
    if i < 65535:
        return "uint16"
    return "uint32"


def guess_datatype(s: str | int | float | None, qd: Any) -> dict[str, Any]:
    """Guess data type of a string value.

    Analyzes a string to determine if it represents an integer, float,
    date, empty value, or remains a string.

    Args:
        s: Value to analyze (can be string, int, float, or None).
        qd: Query date matcher object for date detection.

    Returns:
        Dictionary with 'base' key indicating detected type and optional
        'subtype' or 'pat' keys for additional information.
    """
    attrs = {"base": "str"}
    if s is None:
        return {"base": "empty"}
    if isinstance(s, int):
        return {"base": "int"}
    if isinstance(s, float):
        return {"base": "float"}
    if not isinstance(s, str):
        return {"base": "typed"}
    if s.isdigit():
        if s[0] == "0":
            attrs = {"base": "numstr"}
        else:
            attrs = {"base": "int", "subtype": guess_int_size(int(s))}
    else:
        try:
            float(s)
            attrs = {"base": "float"}
            return attrs
        except ValueError:
            pass
        if qd:
            is_date = False
            res = qd.match(s)
            if res:
                attrs = {"base": "date", "pat": res["pattern"]}
                is_date = True
            if not is_date:
                if len(s.strip()) == 0:
                    attrs = {"base": "empty"}
    return attrs


class TypeGuesser:
    """:func:`guess_datatype` for many values, with cheaper date detection.

    Date matching (qddate) costs up to 0.5 ms per value, which dominated ``stats`` on text
    columns. Results are cached per field and value; values without digits skip the date
    check (every qddate pattern has a day or a year); and after ``date_probe`` checked values
    of a field, dates are only looked for while at least half of them were dates. (Codes
    such as hashes match a date pattern now and then.)

    Args:
        qd: qddate ``DateParser`` (``None`` disables date detection).
        date_probe: Values checked per field before giving up on dates.
        cache_size: Maximum number of cached ``(field, value)`` results.
    """

    def __init__(self, qd: Any, date_probe: int = 1000, cache_size: int = 100_000) -> None:
        self.qd = qd
        self.date_probe = date_probe
        self.cache_size = cache_size
        self._cache: dict[tuple[str, str], str] = {}
        self._probes: dict[str, int] = {}
        self._dates: dict[str, int] = {}

    def base(self, field: str, value: Any) -> str:
        """The base type (``int``, ``float``, ``date``, ``str``, ...) of ``value``."""
        if not isinstance(value, str):
            return str(guess_datatype(value, None)["base"])
        key = (field, value)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        probes = self._probes.get(field, 0)
        check_date = (
            self.qd is not None
            and any(c.isdigit() for c in value)
            and (probes < self.date_probe or self._dates.get(field, 0) * 2 >= probes)
        )
        result = str(guess_datatype(value, self.qd if check_date else None)["base"])
        if check_date and result in ("date", "str", "empty"):
            self._probes[field] = probes + 1
            if result == "date":
                self._dates[field] = self._dates.get(field, 0) + 1
        elif self.qd is not None and result == "str" and not value.strip():
            result = "empty"  # what guess_datatype reports when it checks dates
        if len(self._cache) < self.cache_size:
            self._cache[key] = result
        return result


def buf_count_newlines_gen(fname: str) -> int:
    """Count newlines in a file using buffered reading.

    Efficiently counts newline characters in large files by reading
    in chunks rather than loading entire file into memory.

    Args:
        fname: Path to the file to analyze.

    Returns:
        Integer count of newline characters in the file.
    """

    def _make_gen(reader):
        while True:
            b = reader(2**16)
            if not b:
                break
            yield b

    with open(fname, "rb") as f:
        count = sum(buf.count(b"\n") for buf in _make_gen(f.raw.read))
    return count


def get_dict_keys(iterable: Any, limit: int = 1000) -> list[str]:
    """Get all unique dictionary keys from an iterable of dictionaries.

    Extracts all nested keys from dictionaries, flattening them with dot notation.
    Uses set for O(1) lookup performance instead of O(n) list operations.

    Args:
        iterable: Iterable of dictionaries to process.
        limit: Maximum number of items to process (default: 1000).

    Returns:
        List of unique flattened key paths (e.g., ['field1', 'field2.subfield']).
    """
    n = 0
    keys_set = set()  # Use set for O(1) lookup instead of O(n) list operations
    for item in iterable:
        if limit and n > limit:
            break
        n += 1
        dk = dict_generator(item)
        for i in dk:
            k = ".".join(i[:-1])
            keys_set.add(k)
    return list(keys_set)  # Convert to list for backward compatibility


def _is_flat(item: dict[str, Any]) -> bool:
    """Check if dictionary contains only flat (non-nested) values.

    Args:
        item: Dictionary to check.

    Returns:
        True if dictionary contains no nested structures, False otherwise.
    """
    for v in item.values():
        if isinstance(v, (tuple, list)):
            return False
        if isinstance(v, dict):
            if not _is_flat(v):
                return False
    return True


def normalize_for_json(obj: Any) -> Any:
    """Convert non-JSON-serializable types to JSON-serializable ones.

    Recursively converts UUID objects and other non-serializable types to strings.
    This is needed when writing data from formats like Parquet (which preserve
    UUIDs as UUID objects) to JSON formats like JSONL.

    Args:
        obj: Object to normalize (can be dict, list, tuple, or primitive type)

    Returns:
        Normalized object with non-serializable types converted to strings
    """
    try:
        import uuid

        if isinstance(obj, uuid.UUID):
            return str(obj)
    except ImportError:
        pass  # uuid module not available

    if isinstance(obj, dict):
        return {key: normalize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [normalize_for_json(item) for item in obj]
    else:
        return obj
