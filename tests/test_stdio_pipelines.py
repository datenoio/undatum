"""Standard input/output pipelines (``-`` as input, records on stdout)."""

from __future__ import annotations

import gzip
import io
import json
import os
import subprocess
import sys

import pytest

from undatum.common.stdio import detect_stream_format, spool_stdin, text_format_of
from undatum.common.writer import write_stdout

CSV = "a,b\n3,x\n1,y\n2,z\n5,w\n4,v\n"


def run(args, stdin: bytes | str | None = None, **kwargs):
    """Run ``python -m undatum`` with ``args``; returns the CompletedProcess."""
    if isinstance(stdin, str):
        stdin = stdin.encode("utf8")
    env = {**os.environ, "NO_COLOR": "1"}
    return subprocess.run(
        [sys.executable, "-m", "undatum", *args],
        input=stdin,
        capture_output=True,
        env=env,
        timeout=60,
        check=False,
        **kwargs,
    )


@pytest.fixture
def data_csv(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text(CSV, encoding="utf8")
    return path


@pytest.mark.parametrize(
    "head,expected",
    [
        (b"a,b\n1,2\n", ("csv", None)),
        (b"a\tb\n1\t2\n", ("tsv", None)),
        (b'{"a": 1}\n', ("jsonl", None)),
        (b'  [{"a": 1}]', ("json", None)),
        (b"PAR1\x00\x00", ("parquet", None)),
        (b"\xef\xbb\xbfa,b\n", ("csv", None)),
        (gzip.compress(b'{"a": 1}\n'), ("jsonl", "gz")),
        (b"\x28\xb5\x2f\xfd....", ("csv", "zst")),
    ],
)
def test_detect_stream_format(head, expected):
    assert detect_stream_format(head) == expected


def test_spool_stdin_names_file_after_format():
    path = spool_stdin(stream=io.BytesIO(b'{"a": 1}\n{"a": 2}\n'))
    assert path.endswith(".jsonl")
    with open(path, encoding="utf8") as handle:
        assert handle.read() == '{"a": 1}\n{"a": 2}\n'


def test_spool_stdin_explicit_format_wins():
    path = spool_stdin("tsv", stream=io.BytesIO(b"a,b\n1,2\n"))
    assert path.endswith(".tsv")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("data.csv", "csv"),
        ("data.TSV", "tsv"),
        ("data.ndjson", "jsonl"),
        ("data.jsonl.gz", "jsonl"),
        ("data.parquet", None),
        ("data", None),
        (None, None),
    ],
)
def test_text_format_of(name, expected):
    assert text_format_of(name) == expected


@pytest.mark.parametrize(
    "fmt,expected",
    [
        ("csv", "a,b\n1,x\n2,\n"),
        ("tsv", "a\tb\n1\tx\n2\t\n"),
        ("jsonl", '{"a": 1, "b": "x"}\n{"a": 2, "b": null}\n'),
        ("json", '[\n{"a": 1, "b": "x"},\n{"a": 2, "b": null}\n]\n'),
    ],
)
def test_write_stdout_text_formats(capsys, fmt, expected):
    count = write_stdout([{"a": 1, "b": "x"}, {"a": 2, "b": None}], fmt)
    assert count == 2
    assert capsys.readouterr().out == expected


def test_write_stdout_empty_json_is_valid(capsys):
    assert write_stdout([], "json") == 0
    assert json.loads(capsys.readouterr().out) == []


def test_pipe_csv_into_head():
    result = run(["head", "-", "-n", "3"], stdin=CSV)
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().splitlines() == ["a,b", "3,x", "1,y", "2,z"]


def test_chain_sort_into_head(data_csv):
    sort = run(["sort", str(data_csv), "--by", "a"])
    assert sort.returncode == 0, sort.stderr
    head = run(["head", "-", "-n", "3"], stdin=sort.stdout)
    assert head.returncode == 0, head.stderr
    assert head.stdout.decode().splitlines() == ["a,b", "1,y", "2,z", "3,x"]


def test_chain_sort_into_dedup(data_csv):
    sort = run(["sort", str(data_csv), "--by", "a"])
    dedup = run(["dedup", "-"], stdin=sort.stdout)
    assert dedup.returncode == 0, dedup.stderr
    assert dedup.stdout.decode().splitlines()[0] == "a,b"
    assert len(dedup.stdout.decode().splitlines()) == 6


def test_csv_in_csv_out(data_csv):
    result = run(["head", str(data_csv), "-n", "2"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().splitlines() == ["a,b", "3,x", "1,y"]


def test_explicit_format_out_jsonl(data_csv):
    result = run(["head", str(data_csv), "-n", "2", "--format-out", "jsonl"])
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.decode().splitlines()]
    assert rows == [{"a": "3", "b": "x"}, {"a": "1", "b": "y"}]


def test_jsonl_stdin_keeps_jsonl():
    result = run(["tail", "-", "-n", "1"], stdin='{"a": 1}\n{"a": 2}\n')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"a": 2}


def test_gzip_stdin_is_decompressed():
    result = run(["head", "-", "-n", "1"], stdin=gzip.compress(CSV.encode()))
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().splitlines() == ["a,b", "3,x"]


def test_format_in_overrides_detection():
    result = run(["head", "-", "-n", "1", "--format-in", "tsv"], stdin="a,b\tc\n1,2\t3\n")
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().splitlines() == ["a,b\tc", "1,2\t3"]


def test_binary_format_to_pipe(data_csv):
    result = run(["head", str(data_csv), "--format-out", "parquet"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(b"PAR1")


def test_binary_format_to_terminal_refused(capsys, monkeypatch):
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True, raising=False)
    from undatum.common.errors import ValidationError

    with pytest.raises(ValidationError, match="--output or redirect"):
        write_stdout([{"a": 1}], "parquet")


def test_count_reads_stdin():
    result = run(["count", "-"], stdin=CSV)
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().strip().splitlines()[-1] == "5"


def test_broken_pipe_exits_zero(tmp_path):
    big = tmp_path / "big.csv"
    big.write_text("n\n" + "\n".join(str(i) for i in range(200000)) + "\n", encoding="utf8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "undatum", "head", str(big), "-n", "200000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdout.readline() == b"n\n"
    proc.stdout.close()
    _, stderr = proc.communicate(timeout=60)
    assert proc.returncode == 0, stderr
    assert b"Traceback" not in stderr
    assert b"BrokenPipe" not in stderr


def test_mask_writes_stdout(data_csv):
    result = run(["mask", str(data_csv), "--fields", "b"])
    assert result.returncode == 0, result.stderr
    lines = result.stdout.decode().splitlines()
    assert lines[0] == "a,b"
    assert all(line.endswith(",***") for line in lines[1:])


def test_format_in_is_used_by_the_reader(tmp_path):
    """--format-in reaches iterabledata, including for compressed files without a format suffix."""
    import zipfile

    text = tmp_path / "data.txt"
    text.write_text("a,b\n1,2\n", encoding="utf8")
    result = run(["head", str(text), "-F", "csv"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().splitlines() == ["a,b", "1,2"]

    archive = tmp_path / "data.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("data.jsonl", '{"a": 1}\n{"a": 2}\n')
    result = run(["headers", str(archive), "--format-in", "jsonl"])
    assert result.returncode == 0, result.stderr
    assert result.stdout.decode().split() == ["a"]

    gz = tmp_path / "data.csv.gz"
    gz.write_bytes(gzip.compress(b"a,b\n1,2\n"))
    result = run(["head", str(gz), "-F", "csv", "-O", "jsonl"])
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"a": "1", "b": "2"}
