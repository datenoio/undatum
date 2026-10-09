"""Top-level picklable workers for process-pool parallelism.

Workers must live at module scope so ``ProcessPoolExecutor`` can pickle them.
"""

from __future__ import annotations

from typing import Any


def transform_convert_chunk(payload: tuple[list[dict], list[str], bool]) -> list[dict]:
    """Flatten / pad convert records for one chunk.

    Args:
        payload: ``(chunk, keys, is_flatten)`` where ``keys`` is the flat schema
            key list used when ``is_flatten`` is True.

    Returns:
        Transformed records ready for ``write_bulk``.
    """
    chunk, keys, is_flatten = payload
    if not is_flatten:
        return list(chunk)

    from iterable.helpers.utils import make_flat

    out: list[dict] = []
    for row in chunk:
        # Pad missing schema keys before flattening (matches iterable convert).
        for key in keys:
            if key not in row:
                row[key] = None
        out.append(make_flat(row))
    return out


def validate_rules_chunk(
    payload: tuple[list[Any], int, str, str | None],
) -> tuple[list[dict], int]:
    """Validate one chunk of records against a rule file.

    Args:
        payload: ``(chunk, start_index, rules_path, filter_expr)``.

    Returns:
        ``(violations, records_seen)`` where ``records_seen`` counts rows in the
        chunk (including filtered-out rows for total accounting).
    """
    chunk, start_index, rules_path, filter_expr = payload
    from undatum.common.filter import match_filter
    from undatum.common.validation_rules import parse_validation_rules

    rule_set = parse_validation_rules(rules_path)
    violations: list[dict] = []
    for offset, record in enumerate(chunk):
        record_index = start_index + offset
        if filter_expr and not match_filter(record, filter_expr):
            continue
        violations.extend(rule_set.validate_record(record, record_index))
    return violations, len(chunk)


def stats_accumulate_chunk(
    payload: tuple[list[Any], bool],
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Accumulate field/type stats for one chunk of records.

    Args:
        payload: ``(chunk, nodates)``. When ``nodates`` is False a DateParser is
            created inside the worker (avoids pickling parser state).

    Returns:
        ``(fielddata, fieldtypes, count)`` partial aggregates.
    """
    chunk, nodates = payload
    from undatum.utils import TypeGuesser, dict_generator

    qd = None
    if not nodates:
        from qddate import DateParser

        qd = DateParser(generate=True)
    types = TypeGuesser(qd)

    fielddata: dict[str, Any] = {}
    fieldtypes: dict[str, Any] = {}
    for item in chunk:
        for i in dict_generator(item):
            if len(i) == 0:
                continue
            if i[0].isdigit():
                continue
            if len(i[0]) == 1:
                continue
            k = ".".join(i[:-1])
            v = i[-1]
            if k not in fielddata:
                fielddata[k] = {
                    "key": k,
                    "uniq": {},
                    "n_uniq": 0,
                    "total": 0,
                    "share_uniq": 0.0,
                    "minlen": None,
                    "maxlen": 0,
                    "avglen": 0,
                    "totallen": 0,
                }
            fd = fielddata[k]
            uniqval = fd["uniq"].get(v, 0)
            fd["uniq"][v] = uniqval + 1
            fd["total"] += 1
            if uniqval == 0:
                fd["n_uniq"] += 1
            fl = len(str(v))
            if fd["minlen"] is None:
                fd["minlen"] = fl
            else:
                fd["minlen"] = fl if fl < fd["minlen"] else fd["minlen"]
            fd["maxlen"] = fl if fl > fd["maxlen"] else fd["maxlen"]
            fd["totallen"] += fl

            if k not in fieldtypes:
                fieldtypes[k] = {"key": k, "types": {}}
            ft = fieldtypes[k]
            thetype = types.base(k, v)
            ft["types"][thetype] = ft["types"].get(thetype, 0) + 1

    return fielddata, fieldtypes, len(chunk)


def merge_stats_partials(
    partials: list[tuple[dict[str, Any], dict[str, Any], int]],
) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Merge associative stats partials from parallel workers.

    Args:
        partials: List of ``(fielddata, fieldtypes, count)`` tuples.

    Returns:
        Merged ``(fielddata, fieldtypes, total_count)``.
    """
    fielddata: dict[str, Any] = {}
    fieldtypes: dict[str, Any] = {}
    total = 0
    for fd_part, ft_part, count in partials:
        total += count
        for key, src in fd_part.items():
            if key not in fielddata:
                fielddata[key] = {
                    "key": key,
                    "uniq": dict(src["uniq"]),
                    "n_uniq": src["n_uniq"],
                    "total": src["total"],
                    "share_uniq": 0.0,
                    "minlen": src["minlen"],
                    "maxlen": src["maxlen"],
                    "avglen": 0,
                    "totallen": src["totallen"],
                }
                continue
            dst = fielddata[key]
            for val, cnt in src["uniq"].items():
                prev = dst["uniq"].get(val, 0)
                dst["uniq"][val] = prev + cnt
                if prev == 0:
                    dst["n_uniq"] += 1
            dst["total"] += src["total"]
            if src["minlen"] is not None:
                if dst["minlen"] is None:
                    dst["minlen"] = src["minlen"]
                else:
                    dst["minlen"] = min(dst["minlen"], src["minlen"])
            dst["maxlen"] = max(dst["maxlen"], src["maxlen"])
            dst["totallen"] += src["totallen"]

        for key, src in ft_part.items():
            if key not in fieldtypes:
                fieldtypes[key] = {"key": key, "types": dict(src["types"])}
                continue
            dst = fieldtypes[key]
            for typ, cnt in src["types"].items():
                dst["types"][typ] = dst["types"].get(typ, 0) + cnt

    return fielddata, fieldtypes, total


def frequency_chunk(
    payload: tuple[list[Any], list[str], str | None],
) -> dict[str, int]:
    """Count field-value frequencies for one chunk.

    Args:
        payload: ``(chunk, fields, filter_expr)``.

    Returns:
        Mapping of tab-joined field values to counts.
    """
    chunk, fields, filter_expr = payload
    from undatum.common.filter import match_filter
    from undatum.utils import field_values

    valuedict: dict[str, int] = {}
    for record in chunk:
        if filter_expr is not None and not match_filter(record, filter_expr):
            continue
        try:
            allvals = [field_values(record, field) for field in fields]
            for n1, _ in enumerate(allvals[0]):
                k = "\t".join(str(allvals[n2][n1]) for n2, _ in enumerate(allvals))
                valuedict[k] = valuedict.get(k, 0) + 1
        except (KeyError, IndexError, TypeError):
            continue
    return valuedict


def merge_frequency_partials(partials: list[dict[str, int]]) -> dict[str, int]:
    """Merge frequency Counter-like dicts from parallel workers."""
    merged: dict[str, int] = {}
    for part in partials:
        for key, cnt in part.items():
            merged[key] = merged.get(key, 0) + cnt
    return merged
