"""Tests for the enum command."""

import json
import uuid

import pytest

from undatum.cmds.enumerator import Enumerator
from undatum.common.errors import ValidationError


def _run(tmp_path, options):
    source = tmp_path / "in.jsonl"
    source.write_text('{"name": "Alice"}\n{"name": "Bob"}\n', encoding="utf8")
    out = tmp_path / "out.jsonl"
    Enumerator().enum(str(source), {**options, "output": str(out)})
    return [json.loads(line) for line in out.read_text().splitlines()]


def test_enum_number_type(tmp_path):
    rows = _run(tmp_path, {"type": "number", "field": "row_id", "start": 5})
    assert [r["row_id"] for r in rows] == [5, 6]


def test_enum_uuid_type(tmp_path):
    rows = _run(tmp_path, {"type": "uuid", "field": "uid"})
    assert len({r["uid"] for r in rows}) == 2
    assert all(uuid.UUID(r["uid"]) for r in rows)


def test_enum_constant_type(tmp_path):
    rows = _run(tmp_path, {"type": "constant", "field": "src", "value": "crm"})
    assert [r["src"] for r in rows] == ["crm", "crm"]


def test_enum_unknown_type(tmp_path):
    with pytest.raises(ValidationError, match="Unknown enum type"):
        _run(tmp_path, {"type": "letters"})
