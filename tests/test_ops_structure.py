"""Semantics of the reshaping operations (Python engine)."""

from __future__ import annotations

import pytest

from undatum.ops import (
    CatConfig,
    EnumConfig,
    ExcludeConfig,
    ExplodeConfig,
    FillConfig,
    FixLengthsConfig,
    TailConfig,
    TransposeConfig,
    get_operation,
)

ROWS = [{"id": 1, "tags": "a, b"}, {"id": 2, "tags": None}, {"id": 3, "tags": "c"}]


def apply(name, cfg, rows):
    return list(get_operation(name).apply(rows, cfg))


def test_transpose_one_record_per_field_in_file_order():
    rows = [{"b": 1, "a": "x"}, {"b": 2, "a": "y"}]
    assert apply("transpose", TransposeConfig(), rows) == [
        {"field": "b", "row_0": 1, "row_1": 2},
        {"field": "a", "row_0": "x", "row_1": "y"},
    ]


def test_transpose_accepts_a_one_shot_iterator():
    rows = iter([{"a": 1}, {"a": 2}])
    assert apply("transpose", TransposeConfig(), rows) == [{"field": "a", "row_0": 1, "row_1": 2}]


def test_explode_keeps_null_rows_and_strips_parts():
    out = apply("explode", ExplodeConfig(field="tags"), ROWS)
    assert [(r["id"], r["tags"]) for r in out] == [(1, "a"), (1, "b"), (2, None), (3, "c")]


def test_exclude_on_dotted_key():
    rows = [{"user": {"id": 1}}, {"user": {"id": 2}}]
    cfg = ExcludeConfig(exclude=[{"user": {"id": 2}}], on=("user.id",))
    assert apply("exclude", cfg, rows) == [{"user": {"id": 1}}]


def test_exclude_all_fields_when_no_key_given():
    cfg = ExcludeConfig(exclude=[{"id": 2, "tags": None}])
    assert [r["id"] for r in apply("exclude", cfg, ROWS)] == [1, 3]


def test_fixlengths_pad_and_truncate():
    rows = [{"b": 1, "a": 2}, {"a": 3}]
    assert apply("fixlengths", FixLengthsConfig(value="-"), rows) == [
        {"a": 2, "b": 1},
        {"a": 3, "b": "-"},
    ]
    assert apply("fixlengths", FixLengthsConfig(strategy="truncate"), rows) == [{"a": 2}, {"a": 3}]


def test_cat_columns_and_rows():
    first = [{"a": 1}, {"a": 2}]
    second = [{"b": 9}]
    assert apply("cat", CatConfig(others=(second,), mode="columns"), first) == [
        {"a": 1, "b": 9},
        {"a": 2},
    ]
    assert apply("cat", CatConfig(others=(second,)), first) == [{"a": 1}, {"a": 2}, {"b": 9}]


def test_enum_overwrites_existing_field_in_place():
    out = apply("enum", EnumConfig(field="id", start=10), [{"id": 1, "x": 0}])
    assert out == [{"id": 10, "x": 0}]


def test_tail_window():
    assert apply("tail", TailConfig(limit=2), ({"i": i} for i in range(5))) == [{"i": 3}, {"i": 4}]


@pytest.mark.parametrize(
    "strategy,expected",
    [
        ("forward", ["x", "x", "y", "y"]),
        ("backward", ["x", "y", "y", "-"]),
        ("constant", ["x", "-", "y", "-"]),
    ],
)
def test_fill_strategies(strategy, expected):
    rows = [{"v": "x"}, {"v": ""}, {"v": "y"}, {"v": None}]
    out = apply("fill", FillConfig(fields=("v",), strategy=strategy, value="-"), rows)
    assert [r["v"] for r in out] == expected


DUPES = [
    {"k": 1, "v": "a"},
    {"k": 2, "v": "b"},
    {"k": 1, "v": "c"},
    {"k": 3, "v": "d"},
    {"k": 2, "v": "e"},
]


@pytest.mark.parametrize("memory_keys", [100, 1])  # 1: moves to the disk index midway
@pytest.mark.parametrize(
    "keep,expected",
    [("first", ["a", "b", "d"]), ("last", ["c", "e", "d"])],
)
def test_dedup_keeps_first_appearance_order(memory_keys, keep, expected):
    from undatum.ops import DedupConfig

    cfg = DedupConfig(keys=("k",), keep=keep, memory_keys=memory_keys)
    assert [r["v"] for r in apply("dedup", cfg, DUPES)] == expected


def test_dedup_low_memory_and_nested_values():
    from undatum.ops import DedupConfig

    rows = [{"a": [1, 2], "b": {"x": 1}}, {"a": [1, 2], "b": {"x": 1}}, {"a": [3]}]
    for low_memory in (False, True):
        out = apply("dedup", DedupConfig(low_memory=low_memory), rows)
        assert out == [rows[0], rows[2]]
