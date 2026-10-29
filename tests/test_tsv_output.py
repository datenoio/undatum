"""TSV output, plain or compressed, has one tab-separated header in every writer."""

from __future__ import annotations

import bz2
import csv
import gzip
import io
import json
import random

import pytest
from typer.testing import CliRunner

from undatum.core import app

runner = CliRunner()

RECORDS = [{"id": str(i), "name": f"n{i}", "city": c} for i, c in enumerate(["a b", "c,d", "e"])]


def _text(path):
    data = path.read_bytes()
    if path.name.endswith(".gz"):
        data = gzip.decompress(data)
    elif path.name.endswith(".bz2"):
        data = bz2.decompress(data)
    elif path.name.endswith(".zst"):
        zstandard = pytest.importorskip("zstandard")
        data = zstandard.ZstdDecompressor().decompressobj().decompress(data)
    return data.decode("utf8")


def _records(path):
    text = _text(path)
    header, second = text.splitlines()[:2]
    assert "\t" in header and "," not in header and second != header, (header, second)
    return list(csv.DictReader(io.StringIO(text), delimiter="\t"))


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "in.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in RECORDS), encoding="utf8")
    return path


OUTPUTS = ["out.tsv", "out.tsv.gz", "out.tsv.bz2", "out.tsv.zst"]


@pytest.mark.parametrize("name", OUTPUTS)
@pytest.mark.parametrize("engine", ["python", "auto"])
def test_convert(source, tmp_path, name, engine):
    out = tmp_path / name
    result = runner.invoke(app, ["convert", str(source), str(out), "--engine", engine])
    assert result.exit_code == 0, result.output
    assert sorted(_records(out), key=lambda r: r["id"]) == RECORDS


@pytest.mark.parametrize("name", OUTPUTS)
@pytest.mark.parametrize(
    "command", [["head"], ["select", "--fields", "id,name,city"], ["sort", "--by", "id"]]
)
def test_record_commands(source, tmp_path, name, command):
    out = tmp_path / name
    result = runner.invoke(app, [command[0], str(source), *command[1:], "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert _records(out) == RECORDS


def test_format_out_tsv(source, tmp_path):
    out = tmp_path / "out.txt"
    args = ["head", str(source), "--output", str(out), "--format-out", "tsv"]
    assert runner.invoke(app, args).exit_code == 0
    assert _records(out) == RECORDS


def test_old_output_file_is_not_sniffed(source, tmp_path):
    out = tmp_path / "out.csv"
    out.write_text("a;b\n1;2\n", encoding="utf8")
    args = ["convert", str(source), str(out), "--engine", "python"]
    assert runner.invoke(app, args).exit_code == 0
    assert out.read_text(encoding="utf8").splitlines()[0] == "city,id,name"


def test_compression_level_applies(tmp_path):
    rng = random.Random(1)
    source = tmp_path / "in.jsonl"
    source.write_text(
        "".join(
            json.dumps({"id": i, "word": rng.choice(["alpha", "beta", "gamma"]) * 3}) + "\n"
            for i in range(5000)
        ),
        encoding="utf8",
    )
    sizes = {}
    for level in (1, 9):
        out = tmp_path / f"out{level}.tsv.gz"
        args = ["convert", str(source), str(out), "--engine", "python", "--level", str(level)]
        assert runner.invoke(app, args).exit_code == 0
        assert len(_records(out)) == 5000
        sizes[level] = out.stat().st_size
    assert sizes[9] < sizes[1]
