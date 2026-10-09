"""JSON output of informational commands, JSON errors, and the published layouts."""

from __future__ import annotations

import bz2
import gzip
import importlib.util
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from undatum.common.errors import FileNotFoundError as UndatumFileNotFound
from undatum.common.errors import error_code, exit_code_for
from undatum.common.results import SCHEMAS, error_document, json_requested
from undatum.core import app

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.csv").write_text("id,name,city\n1,Alice,Paris\n2,Bob,Rome\n3,Carol,Paris\n")
    (tmp_path / "b.csv").write_text("id,name,city\n1,Alice,Paris\n2,Bob,Berlin\n4,Dan,Rome\n")
    (tmp_path / "v.csv").write_text("id,email\n1,a@example.com\n2,not-an-email\n")
    (tmp_path / "rules.yml").write_text(
        "rules:\n  - field: email\n    name: Email required\n    required: true\n"
    )
    return tmp_path


def _json(args: list[str]) -> dict:
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


CASES = [
    (["count", "a.csv", "--json"], "undatum.count/1"),
    (["count", "a.csv", "-O", "json"], "undatum.count/1"),
    (["headers", "a.csv", "--json"], "undatum.headers/1"),
    (["sniff", "a.csv", "--json"], "undatum.sniff/1"),
    (["stats", "a.csv", "--json"], "undatum.stats/1"),
    (["schema", "a.csv", "--json"], "undatum.schema/1"),
    (["schema", "a.csv", "--validate", "--json"], "undatum.schema-validation/1"),
    (["diff", "a.csv", "b.csv", "--key", "id", "--json"], "undatum.diff/1"),
    (["validate", "v.csv", "--rules", "rules.yml", "--json"], "undatum.validate/1"),
    (
        ["validate", "v.csv", "--fields", "email", "--rule", "common.email", "--json"],
        "undatum.validate-rule/1",
    ),
    (["analyze", "a.csv", "--json"], "undatum.analyze/1"),
    (["formats", "list", "--json"], "undatum.formats/1"),
    (["config", "show", "--json"], "undatum.config/1"),
]


@pytest.mark.parametrize(("args", "schema_id"), CASES, ids=[" ".join(c[0][:2]) for c in CASES])
def test_document_matches_its_layout(files, args, schema_id):
    document = _json(args)
    layout = SCHEMAS[schema_id]
    assert document["schema"] == schema_id
    assert set(document) <= {"schema", *layout.properties}, set(document) - set(layout.properties)
    assert set(layout.required) <= set(document)
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.validate(document, layout.json_schema())


def test_count_document(files):
    assert _json(["count", "a.csv", "--json"]) == {
        "schema": "undatum.count/1",
        "file": "a.csv",
        "rows": 3,
    }


def test_headers_keep_file_order(files):
    assert _json(["headers", "a.csv", "--json"])["fields"] == ["id", "name", "city"]


def test_sniff_document(files):
    document = _json(["sniff", "a.csv", "--json"])
    assert document["filetype"] == "csv"
    assert document["compression"] is None
    assert document["delimiter"] == ","
    assert document["has_header"] is True
    assert document["record_count"] == 3
    assert list(document["fields"]) == ["id", "name", "city"]


def test_diff_document_is_the_only_stdout(files):
    result = CliRunner().invoke(app, ["diff", "a.csv", "b.csv", "--key", "id", "--json"])
    document = json.loads(result.stdout)
    assert document["summary"]["changed_count"] == 1
    assert document["key"] == ["id"]
    assert "Summary:" in result.stderr


def test_validate_rule_document(files):
    document = _json(["validate", "v.csv", "--fields", "email", "--rule", "common.email", "--json"])
    assert document["statistics"]["invalid"] == 1
    assert document["records"] == [{"email": "not-an-email", "email_valid": False}]


def test_record_commands_print_arrays(files):
    rows = _json(["frequency", "a.csv", "-f", "city", "--json"])
    assert {"city": "Paris", "count": 2} in rows


# ------------------------------------------------------------------------ JSON errors


def _run(args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "undatum", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        check=False,
    )


def test_error_is_json_on_stderr(files):
    result = _run(["stats", "missing.csv", "--json"], files)
    assert result.returncode == 1
    assert result.stdout == ""
    error = json.loads(result.stderr)["error"]
    assert error["code"] == "file_not_found"
    assert error["details"] == {"file_path": "missing.csv"}


def test_usage_error_is_json(files):
    result = _run(["count", "a.csv", "--bogus", "--json"], files)
    assert result.returncode == 2
    assert json.loads(result.stderr)["error"]["code"] == "usage_error"


def test_errors_stay_text_without_json(files):
    result = _run(["stats", "missing.csv"], files)
    assert result.returncode == 1
    assert result.stderr.startswith("Error: File not found")


def test_json_requested():
    assert json_requested(["count", "x.csv", "--json"])
    assert json_requested(["stats", "x.csv", "-O", "json"])
    assert json_requested(["stats", "x.csv", "--format-out=JSON"])
    assert json_requested(["stats", "x.csv", "-Ojson"])
    assert not json_requested(["head", "x.csv", "-O", "csv"])
    assert not json_requested(["sql", "--", "--json"])


def test_error_codes():
    assert error_code(UndatumFileNotFound("x.csv")) == "file_not_found"
    assert (error_code(FileNotFoundError("x")), exit_code_for(FileNotFoundError("x"))) == (
        "file_not_found",
        1,
    )
    assert (error_code(ValueError("x")), exit_code_for(ValueError("x"))) == ("invalid_value", 1)
    assert (error_code(ImportError("x")), exit_code_for(ImportError("x"))) == (
        "dependency_missing",
        2,
    )
    assert (error_code(RuntimeError("x")), exit_code_for(RuntimeError("x"))) == (
        "internal_error",
        4,
    )
    document = error_document(UndatumFileNotFound("x.csv"), 1)
    assert document["error"]["code"] == "file_not_found"


# ------------------------------------------------------------------- published layouts


def test_published_schemas_are_current():
    spec = importlib.util.spec_from_file_location(
        "generate_result_schemas", ROOT / "scripts" / "generate_result_schemas.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.main(["--check"]) == 0, "run scripts/generate_result_schemas.py"


def test_schema_ids_are_versioned():
    for schema_id, layout in SCHEMAS.items():
        name, _, version = schema_id.partition("/")
        assert name.startswith("undatum.") and version.isdigit(), schema_id
        assert layout.id == schema_id


# ---------------------------------------------------- delimiters of compressed CSV files


@pytest.mark.parametrize("suffix", ["gz", "bz2", "zip"])
def test_compressed_csv_delimiter_is_detected(tmp_path, suffix):
    data = b"a;b\n1;x\n"
    path = tmp_path / f"c.csv.{suffix}"
    if suffix == "gz":
        path.write_bytes(gzip.compress(data))
    elif suffix == "bz2":
        path.write_bytes(bz2.compress(data))
    else:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("c.csv", data)
    result = CliRunner().invoke(app, ["headers", str(path), "--json"])
    assert json.loads(result.stdout)["fields"] == ["a", "b"]
    sniffed = json.loads(CliRunner().invoke(app, ["sniff", str(path), "--json"]).stdout)
    assert (sniffed["delimiter"], sniffed["compression"]) == (";", suffix)


# --------------------------------------------------------- agent tools share the layouts


def test_agent_tools_return_cli_documents(files):
    from undatum.tools import schemas
    from undatum.tools.sandbox import configure_sandbox

    configure_sandbox(files)
    try:

        def same(tool_doc, cli_doc):
            # Tools report the sandbox-resolved (absolute) path.
            assert tool_doc.pop("file").endswith(cli_doc.pop("file"))
            assert tool_doc == cli_doc

        same(
            schemas.call_tool("count_records", {"path": "a.csv"})["data"],
            _json(["count", "a.csv", "--json"]),
        )
        same(
            schemas.call_tool("list_fields", {"path": "a.csv"})["data"],
            _json(["headers", "a.csv", "--json"]),
        )
        sniffed = schemas.call_tool("sniff_file", {"path": "a.csv"})
        assert sniffed["data"]["schema"] == "undatum.sniff/1"
        diff = schemas.call_tool(
            "diff_files", {"left_path": "a.csv", "right_path": "b.csv", "key": ["id"]}
        )
        cli = _json(["diff", "a.csv", "b.csv", "--key", "id", "--json"])
        assert diff["data"]["summary"] == cli["summary"]
        assert diff["data"]["changed"] == cli["changed"]
        outside = schemas.call_tool(
            "diff_files", {"left_path": "a.csv", "right_path": "/etc/hosts"}
        )
        assert outside["code"] == "path_outside_root"
    finally:
        configure_sandbox(allow_anywhere=True)


def test_mcp_registers_informational_tools(files):
    pytest.importorskip("mcp")
    import asyncio

    from undatum.mcp.server import create_mcp_server

    server = create_mcp_server(root=str(files))
    names = {tool.name for tool in asyncio.run(server.list_tools())}
    assert {"count_records", "list_fields", "sniff_file", "diff_files"} <= names
