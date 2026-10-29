"""DuckDB reads a CSV header as the Python reader does: the first line, names as written."""

from __future__ import annotations

import gzip
import json

import duckdb
import pytest
from typer.testing import CliRunner

from undatum.common.command_utils import (
    duckdb_csv_names,
    duckdb_read_csv_expr,
    duckdb_read_expr,
    read_csv_header,
)
from undatum.core import app
from undatum.io import RowSource

runner = CliRunner()

# Files whose header DuckDB's sniffer used to read differently from the Python reader.
MESSY = {
    "numeric_header": "1,2\n3,4\n5,6\n",
    "padded_names": " a , b \n1,2\n",
    "quoted_name": '"a,b",c\n1,2\n',
    "special_names": 'it\'s,"q""x",back\\slash,é ü\n1,2,3,4\n',
    "short_row": "a,b\n1,2\n3\n",
    "quoted_newline": 'a,b\r\n1,"x\r\ny"\r\n3,4\r\n',
    "only_header": "a,b\n",
    "empty_file": "",
    "repeated_names": "a,a,b\n1,2,3\n",
    "names_by_case": "a,A,b\n1,2,3\n",
    "empty_name": "a,,b\n1,2,3\n",
}


def _write(tmp_path, text, name="data.csv"):
    path = tmp_path / name
    path.write_bytes(text.encode("utf8"))
    return str(path)


def _cli(*args):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.output


def _jsonl(text):
    return [json.loads(line) for line in text.splitlines()]


class TestReadCsvHeader:
    def test_first_line_as_written(self, tmp_path):
        path = _write(tmp_path, ' a ,"b,c",1\n1,2,3\n')
        assert read_csv_header(path, ",") == [" a ", "b,c", "1"]

    def test_quotechar_and_delimiter(self, tmp_path):
        path = _write(tmp_path, "'a;b';c\n")
        assert read_csv_header(path, ";", quotechar="'") == ["a;b", "c"]

    def test_gzip(self, tmp_path):
        path = tmp_path / "data.csv.gz"
        path.write_bytes(gzip.compress(b"x,y\n1,2\n"))
        assert read_csv_header(str(path), ",", codec="gz") == ["x", "y"]

    def test_byte_order_mark_is_kept(self, tmp_path):
        # The Python reader keeps it in the first name; duckdb_csv_names drops it.
        assert read_csv_header(_write(tmp_path, "\ufeffa,b\n"), ",") == ["\ufeffa", "b"]

    def test_empty_and_missing_files(self, tmp_path):
        assert read_csv_header(_write(tmp_path, ""), ",") == []
        assert read_csv_header(str(tmp_path / "missing.csv"), ",") is None


@pytest.mark.parametrize(
    "header,names",
    [
        (["a", " b ", "1"], ["a", " b ", "1"]),
        (["\ufeffa", "b"], ["a", "b"]),
        (["a", "a"], None),
        (["a", "A"], None),
        (["a", ""], None),
        ([], None),
        (None, None),
    ],
)
def test_duckdb_csv_names(header, names):
    assert duckdb_csv_names(header) == names


def test_read_expression_names_the_columns(tmp_path):
    path = _write(tmp_path, "it's,b\n1,2\n")
    expr = duckdb_read_csv_expr(path, ",", header=["it's", "b"])
    assert "auto_detect=false" in expr and "header=true" in expr
    assert duckdb.sql(f"SELECT * FROM {expr}").fetchall() == [("1", "2")]
    assert duckdb.sql(f"SELECT * FROM {expr}").columns == ["it's", "b"]


def test_read_expression_uses_the_quotechar(tmp_path):
    path = _write(tmp_path, "a,b\n'1,5',2\n")
    expr = duckdb_read_expr(path, "csv", {"quotechar": "'"}, all_varchar=True)
    assert duckdb.sql(f"SELECT * FROM {expr}").fetchall() == [("1,5", "2")]


@pytest.mark.parametrize(
    "name",
    [
        "numeric_header",
        "padded_names",
        "quoted_name",
        "special_names",
        "quoted_newline",
        "only_header",
    ],
)
def test_duckdb_reads_the_rows_of_the_python_reader(tmp_path, name):
    path = _write(tmp_path, MESSY[name])
    result = duckdb.sql(f"SELECT * FROM {RowSource(path).duckdb_from()}")
    assert [dict(zip(result.columns, row, strict=True)) for row in result.fetchall()] == list(
        RowSource(path)
    )


@pytest.mark.parametrize("name", ["repeated_names", "names_by_case", "empty_name", "empty_file"])
def test_headers_duckdb_cannot_name_use_python(tmp_path, name):
    path = _write(tmp_path, MESSY[name])
    with pytest.raises(ValueError):
        duckdb_read_expr(path, "csv", {}, all_varchar=True)
    assert RowSource(path).duckdb_from() is None


@pytest.mark.parametrize("name", list(MESSY))
@pytest.mark.parametrize(
    "command",
    [
        ["count"],
        ["head", "-O", "jsonl"],
        ["select", "-f", "{first}", "-O", "jsonl"],
        ["sort", "--by", "{first}", "-O", "jsonl"],
        ["frequency", "-f", "{first}"],
        ["uniq", "-f", "{first}"],
    ],
    ids=lambda command: command[0],
)
def test_engines_agree(tmp_path, name, command):
    path = _write(tmp_path, MESSY[name])
    header = read_csv_header(path, ",") or ["a"]
    args = [arg.replace("{first}", header[0]) for arg in command]
    outputs = {
        engine: _cli(args[0], "-e", engine, path, *args[1:]) for engine in ("python", "auto")
    }
    if args[0] in ("frequency", "uniq"):
        # DuckDB does not keep the first-seen order of ties.
        outputs = {engine: sorted(text.splitlines()) for engine, text in outputs.items()}
    assert outputs["auto"] == outputs["python"]


@pytest.mark.parametrize("name", list(MESSY))
def test_convert_engines_agree(tmp_path, name):
    path = _write(tmp_path, MESSY[name])
    outputs = {}
    for engine in ("python", "auto"):
        out = tmp_path / f"{engine}.jsonl"
        _cli("convert", "-e", engine, path, str(out))
        outputs[engine] = _jsonl(out.read_text(encoding="utf8"))
    assert outputs["auto"] == outputs["python"]


def test_byte_order_mark_is_dropped(tmp_path):
    # DuckDB drops it, as before; the Python reader keeps it in the first name.
    path = _write(tmp_path, "\ufeffa,b\n1,2\n")
    assert _jsonl(_cli("head", "-e", "duckdb", path, "-O", "jsonl")) == [{"a": "1", "b": "2"}]


def test_long_rows_keep_the_header(tmp_path):
    # DuckDB's sniffer took the long row for the header and lost the rows before it.
    path = _write(tmp_path, "a,b\n1,2\n3,4,5\n6,7\n")
    assert _cli("count", "-e", "duckdb", path).strip() == "3"
    out = tmp_path / "out.jsonl"
    _cli("convert", "-e", "duckdb", path, str(out))
    assert _jsonl(out.read_text(encoding="utf8")) == [
        {"a": "1", "b": "2"},
        {"a": "3", "b": "4"},
        {"a": "6", "b": "7"},
    ]
