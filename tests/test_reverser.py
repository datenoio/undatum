"""Tests for the reverse command (disk-backed for large inputs)."""

import json

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
