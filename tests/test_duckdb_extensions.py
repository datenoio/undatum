"""DuckDB extensions installed ahead of time, and non-UTF-8 CSV read with ``encodings``."""

from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from undatum.common import duckdb_extensions as ext
from undatum.common.command_utils import duckdb_csv_encoding
from undatum.common.engine_selector import detect_engine
from undatum.common.errors import ConfigurationError
from undatum.core import app
from undatum.io import RowSource

runner = CliRunner()
CP1251 = str(Path(__file__).parent / "fixtures" / "ru_cp1251_comma.csv")


def _fake_install(directory, *names):
    for name in names:
        path = Path(ext.extension_path(name, str(directory)))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 1024)


class _FakeConnection:
    """Records install calls and writes the extension file as DuckDB would."""

    def __init__(self, directory, fail=False):
        self.directory = directory
        self.fail = fail
        self.installed = []

    def install_extension(self, name, force_install=False):
        if self.fail:
            raise duckdb.IOException("Failed to download extension")
        self.installed.append(name)
        _fake_install(self.directory, name)

    def load_extension(self, name):
        pass

    def close(self):
        pass


@pytest.fixture
def fake_duckdb(monkeypatch, tmp_path):
    ext.extension_path("excel")  # DuckDB's version and platform, before connect is replaced
    connections = []

    def connect(config=None, **kwargs):
        connections.append(_FakeConnection(config["extension_directory"]))
        return connections[-1]

    monkeypatch.setattr(duckdb, "connect", connect)
    return connections


class TestStatus:
    def test_nothing_installed(self, tmp_path):
        rows = ext.extension_status(str(tmp_path))
        assert [row["name"] for row in rows] == ["encodings", "excel", "httpfs", "spatial"]
        assert not any(row["installed"] for row in rows)

    def test_installed_file(self, tmp_path):
        _fake_install(tmp_path, "excel")
        rows = {row["name"]: row for row in ext.extension_status(str(tmp_path))}
        assert rows["excel"]["installed"] and rows["excel"]["size"] == 1024
        assert not rows["httpfs"]["installed"]

    def test_directory_from_environment(self, tmp_path, monkeypatch):
        monkeypatch.setenv("UNDATUM_DUCKDB_EXTENSION_DIR", str(tmp_path))
        _fake_install(tmp_path, "spatial")
        assert ext.extension_directory() == str(tmp_path)
        assert ext.extension_installed("spatial")
        assert not ext.extension_installed("excel")


class TestInstall:
    def test_downloads_only_missing(self, fake_duckdb, tmp_path):
        _fake_install(tmp_path, "excel")
        rows = ext.install_extensions(["excel", "httpfs"], str(tmp_path))
        assert fake_duckdb[0].installed == ["httpfs"]
        assert [(row["name"], row["downloaded"]) for row in rows] == [
            ("excel", False),
            ("httpfs", True),
        ]

    def test_force_downloads_again(self, fake_duckdb, tmp_path):
        _fake_install(tmp_path, "excel")
        ext.install_extensions(["excel"], str(tmp_path), force=True)
        assert fake_duckdb[0].installed == ["excel"]

    def test_download_failure_is_a_configuration_error(self, monkeypatch, tmp_path):
        ext.extension_path("excel")
        monkeypatch.setattr(duckdb, "connect", lambda config=None: _FakeConnection(tmp_path, True))
        with pytest.raises(ConfigurationError) as info:
            ext.install_extensions(["excel"], str(tmp_path))
        assert info.value.exit_code == 2


class TestCommand:
    def test_list_json(self, tmp_path):
        _fake_install(tmp_path, "httpfs")
        result = runner.invoke(app, ["extensions", "list", "--dir", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        document = json.loads(result.output)
        assert document["schema"] == "undatum.extensions/1"
        assert document["directory"] == str(tmp_path)
        installed = {row["name"]: row["installed"] for row in document["extensions"]}
        assert installed == {"encodings": False, "excel": False, "httpfs": True, "spatial": False}

    def test_install_all_by_default(self, fake_duckdb, tmp_path):
        result = runner.invoke(app, ["extensions", "install", "--dir", str(tmp_path), "--json"])
        assert result.exit_code == 0, result.output
        assert fake_duckdb[0].installed == ["encodings", "excel", "httpfs", "spatial"]
        assert all(row["installed"] for row in json.loads(result.output)["extensions"])

    def test_unknown_extension(self, tmp_path):
        result = runner.invoke(app, ["extensions", "install", "nope", "--dir", str(tmp_path)])
        assert result.exit_code == 1
        assert "Unknown extension: nope" in str(result.exception)


class TestWithoutEncodings:
    """Without the extension, non-UTF-8 CSV stays on the Python engine and nothing downloads."""

    def test_python_engine(self, monkeypatch):
        def no_download(*args, **kwargs):
            raise AssertionError("a DuckDB connection was opened to check encodings")

        monkeypatch.setattr(ext, "_encoding_names", no_download)
        assert duckdb_csv_encoding(CP1251) is None
        assert RowSource(CP1251).duckdb_from() is None
        assert detect_engine(CP1251, "auto", "csv") == "iterable"

    def test_utf8_needs_no_extension(self, tmp_path):
        path = tmp_path / "utf8.csv"
        path.write_text("a,b\nПривет,1\n", encoding="utf8")
        assert duckdb_csv_encoding(str(path)) == "utf-8"

    def test_explicit_utf8_on_other_text(self):
        assert duckdb_csv_encoding(CP1251, encoding="utf-8") is None


def test_ascii_incompatible_encodings_stay_on_python(installed_extensions):
    assert ext.duckdb_encoding_name("utf-16") is None
    assert ext.duckdb_encoding_name("no-such-encoding") is None
    assert ext.duckdb_encoding_name("cp1251") == "cp1251"


class TestWithEncodings:
    """Records equal the Python engine's when DuckDB reads Windows-1251 with ``encodings``."""

    def test_duckdb_reads_the_file(self, installed_extensions):
        assert duckdb_csv_encoding(CP1251) == "windows-1251"
        assert "encoding='windows-1251'" in RowSource(CP1251).duckdb_from()
        assert detect_engine(CP1251, "auto", "csv") == "duckdb"

    def test_rows_match_the_python_reader(self, installed_extensions):
        source = RowSource(CP1251)
        conn = duckdb.connect(config={"extension_directory": installed_extensions})
        result = conn.execute(f"SELECT * FROM {source.duckdb_from()}")
        names = [column[0] for column in result.description]
        rows = [
            {name: "" if value is None else value for name, value in zip(names, row, strict=True)}
            for row in result.fetchall()
        ]
        assert rows == list(source)

    @pytest.mark.parametrize(
        "command",
        [
            ["count"],
            ["select", "-f", "inn,status", "-O", "jsonl"],
            ["frequency", "-f", "status"],
            ["uniq", "-f", "status"],
        ],
        ids=lambda command: command[0],
    )
    def test_cli_engines_agree(self, installed_extensions, command):
        outputs = {}
        for engine in ("python", "auto"):
            result = runner.invoke(app, [command[0], "-e", engine, CP1251, *command[1:]])
            assert result.exit_code == 0, result.output
            outputs[engine] = result.output
        assert outputs["auto"] == outputs["python"]

    @pytest.mark.parametrize("suffix", ["jsonl", "parquet"])
    def test_convert(self, installed_extensions, tmp_path, suffix):
        import pyarrow.parquet as pq

        records = {}
        for engine in ("python", "auto"):
            out = tmp_path / f"{engine}.{suffix}"
            args = ["convert", "-e", engine, "--encoding", "cp1251", CP1251, str(out)]
            result = runner.invoke(app, args)
            assert result.exit_code == 0, result.output
            if suffix == "jsonl":
                records[engine] = [json.loads(line) for line in out.read_text().splitlines()]
            else:
                records[engine] = pq.read_table(out).to_pylist()
        assert records["auto"] == records["python"]
        assert len(records["auto"]) == 17


def test_environment_points_at_the_test_directory():
    assert os.environ["UNDATUM_DUCKDB_EXTENSION_DIR"]
    assert not ext.extension_installed("encodings")
