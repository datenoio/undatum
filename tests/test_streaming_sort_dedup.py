"""Tests for external merge sort and disk-backed dedup helpers."""

from undatum.cmds.deduplicator import Deduplicator
from undatum.cmds.sorter import Sorter
from undatum.common.disk_dedup import DiskDeduplicator
from undatum.common.external_sort import external_merge_sort


def test_external_merge_sort_orders_records():
    records = [{"n": i} for i in [5, 1, 4, 2, 3, 9, 0, 8, 7, 6]]
    sorted_rows = list(external_merge_sort(records, key_fn=lambda r: r["n"], run_size=3))
    assert [r["n"] for r in sorted_rows] == list(range(10))


def test_external_merge_sort_descending():
    records = [{"n": i} for i in range(10)]
    sorted_rows = list(
        external_merge_sort(records, key_fn=lambda r: r["n"], reverse=True, run_size=4)
    )
    assert [r["n"] for r in sorted_rows] == list(range(9, -1, -1))


def test_disk_dedup_keep_first():
    rows = [
        {"id": 1, "v": "a"},
        {"id": 1, "v": "b"},
        {"id": 2, "v": "c"},
    ]
    with DiskDeduplicator(keep="first") as deduper:
        out = list(deduper.process(rows, key_fn=lambda r: r["id"]))
    assert out == [{"id": 1, "v": "a"}, {"id": 2, "v": "c"}]


def test_disk_dedup_keep_last():
    rows = [
        {"id": 1, "v": "a"},
        {"id": 1, "v": "b"},
        {"id": 2, "v": "c"},
    ]
    with DiskDeduplicator(keep="last") as deduper:
        out = list(deduper.process(rows, key_fn=lambda r: r["id"]))
    assert {(r["id"], r["v"]) for r in out} == {(1, "b"), (2, "c")}


def test_sorter_low_memory(tmp_path):
    src = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    src.write_text('{"n": 2}\n{"n": 1}\n{"n": 3}\n', encoding="utf-8")
    Sorter().sort(
        str(src),
        {"by": "n", "output": str(out), "low_memory": True, "engine": "python", "run_size": 1},
    )
    lines = [line for line in out.read_text(encoding="utf-8").splitlines() if line]
    assert '"n":1' in lines[0].replace(" ", "")
    assert '"n":3' in lines[-1].replace(" ", "")


def test_dedup_low_memory(tmp_path):
    src = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    src.write_text(
        '{"id": 1, "v": "a"}\n{"id": 1, "v": "b"}\n{"id": 2, "v": "c"}\n',
        encoding="utf-8",
    )
    Deduplicator().dedup(
        str(src),
        {
            "key_fields": "id",
            "keep": "first",
            "output": str(out),
            "low_memory": True,
            "engine": "python",
        },
    )
    text = out.read_text(encoding="utf-8")
    assert text.count('"id": 1') + text.count('"id":1') == 1
    assert "2" in text


def test_dedup_duckdb_file_output_has_no_rn_column(tmp_path):
    """The DuckDB COPY path must not leak the internal row-number column."""
    import json

    src = tmp_path / "in.jsonl"
    out = tmp_path / "out.jsonl"
    src.write_text(
        '{"id": 1, "v": "a"}\n{"id": 1, "v": "b"}\n{"id": 2, "v": "c"}\n',
        encoding="utf-8",
    )
    Deduplicator().dedup(
        str(src),
        {"key_fields": "id", "keep": "first", "output": str(out), "engine": "duckdb"},
    )
    rows = [
        json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(rows) == 2
    for row in rows:
        assert set(row.keys()) == {"id", "v"}
