"""Tests for the reverse command (disk-backed for large inputs)."""

import datetime
import json
from decimal import Decimal

import pytest

from undatum.cmds.reverser import Reverser
from undatum.ops.spill import reversed_rows


def test_reverse_basic(tmp_path):
    source = tmp_path / "in.jsonl"
    source.write_text('{"id": 1}\n{"id": 2}\n{"id": 3}\n', encoding="utf8")
    out = tmp_path / "out.jsonl"
    Reverser().reverse(str(source), {"output": str(out)})
    assert [json.loads(line)["id"] for line in out.read_text().splitlines()] == [3, 2, 1]


def test_reversed_rows_spills_in_chunks():
    rows = ({"id": i} for i in range(25))
    assert [r["id"] for r in reversed_rows(rows, chunk_rows=4)] == list(range(24, -1, -1))


def test_reversed_rows_removes_spill_files(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    list(reversed_rows(({"id": i} for i in range(10)), chunk_rows=3))
    assert list(tmp_path.iterdir()) == []


def test_spill_keeps_typed_nested_values_and_literal_tags():
    import uuid

    value = {
        "day": datetime.date(2026, 1, 2),
        "stamp": datetime.datetime(2026, 1, 2, 3, tzinfo=datetime.UTC, fold=1),
        "time": datetime.time(3, 4, 5, fold=1),
        "duration": datetime.timedelta(days=2, microseconds=3),
        "amount": Decimal("123.4500"),
        "binary": b"\0\xff\n",
        "uuid": uuid.uuid4(),
        "nested": [{"a": (Decimal("1.2"),)}],
        "keys": {1: "integer", "1": "string"},
        "large": 2**100,
        "literal": {"__undatum_spill_type__": "date", "value": "not-a-date"},
    }
    rows = [{**value, "i": i} for i in range(5)]
    out = list(reversed_rows(rows, chunk_rows=2))
    assert out == list(reversed(rows))
    for row in out:
        assert isinstance(row["amount"], Decimal)
        assert isinstance(row["binary"], bytes)
        assert isinstance(row["nested"][0]["a"], tuple)
        assert row["stamp"].fold == row["time"].fold == 1


def test_backward_fill_preserves_types_when_both_passes_spill():
    from undatum.ops import FillConfig, get_operation
    from undatum.ops.spill import DEFAULT_CHUNK_ROWS

    day, price = datetime.date(2026, 1, 2), Decimal("1.50")
    rows = ({"day": None if i == 0 else day, "price": price} for i in range(DEFAULT_CHUNK_ROWS + 1))
    out = get_operation("fill").apply(rows, FillConfig(fields=("day",), strategy="backward"))
    assert all(row == {"day": day, "price": price} for row in out)


def test_failed_spill_does_not_leave_temporary_files(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with pytest.raises(TypeError):
        list(reversed_rows([{"unsupported": object()}], chunk_rows=1))
    assert list(tmp_path.iterdir()) == []
