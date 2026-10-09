"""Agent tools generated from the operation registry."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from undatum.ops import REGISTRY, get_operation
from undatum.tools import generated, schemas
from undatum.tools.sandbox import configure_sandbox


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.csv").write_text("id,name\n1,a\n1,a\n2,b\n", encoding="utf8")
    (tmp_path / "keys.csv").write_text("id\n2\n", encoding="utf8")
    configure_sandbox(tmp_path)
    yield tmp_path
    configure_sandbox(allow_anywhere=True)


def test_every_operation_has_a_tool():
    get_operation("head")
    names = {tool["name"] for tool in schemas.TOOL_DEFINITIONS}
    assert set(REGISTRY) - set(generated.EXCLUDED) <= names


def test_schema_from_config_dataclass():
    tool = next(t for t in generated.tool_definitions() if t["name"] == "dedup")
    properties = tool["parameters"]["properties"]
    assert properties["keep"]["enum"] == ["first", "last"]
    assert properties["keep"]["default"] == "first"
    assert properties["keys"]["type"] == "array"
    assert "Key fields" in properties["keys"]["description"]
    assert tool["parameters"]["required"] == ["input_path"]
    join = next(t for t in generated.tool_definitions() if t["name"] == "join")
    assert "right_path" in join["parameters"]["properties"]
    assert "right_path" in join["parameters"]["required"]


def test_inline_result_without_output(data):
    result = schemas.call_tool("dedup", {"input_path": "x.csv"})
    assert result["ok"], result
    assert result["data"]["records"] == [{"id": "1", "name": "a"}, {"id": "2", "name": "b"}]


def test_inline_result_is_limited(data):
    result = schemas.call_tool("head", {"input_path": "x.csv", "limit": 1})
    assert result["data"]["count"] == 1 and result["data"]["truncated"] is True


def test_writing_requires_confirm(data):
    result = schemas.call_tool("dedup", {"input_path": "x.csv", "output_path": "out.csv"})
    assert result["code"] == "confirmation_required"
    assert not (data / "out.csv").exists()
    result = schemas.call_tool(
        "dedup", {"input_path": "x.csv", "output_path": "out.csv", "confirm": True}
    )
    assert result["ok"], result
    assert (data / "out.csv").read_text().splitlines() == ["id,name", "1,a", "2,b"]


def test_other_input_paths_are_sandboxed(data):
    result = schemas.call_tool(
        "exclude", {"input_path": "x.csv", "exclude_path": "keys.csv", "on": ["id"]}
    )
    assert [r["id"] for r in result["data"]["records"]] == ["1", "1"]
    outside = schemas.call_tool(
        "exclude", {"input_path": "x.csv", "exclude_path": "../keys.csv", "on": ["id"]}
    )
    assert outside["code"] == "path_outside_root"
    many = schemas.call_tool("cat", {"input_path": "x.csv", "others_paths": ["/etc/passwd"]})
    assert many["code"] == "path_outside_root"


def test_invalid_arguments(data):
    assert schemas.call_tool("head", {})["code"] == "invalid_arguments"
    assert (
        schemas.call_tool("head", {"input_path": "x.csv", "bogus": 1})["code"]
        == "invalid_arguments"
    )


def test_parity_report_lists_commands():
    rows = {row["command"]: row for row in generated.parity_report()}
    assert rows["dedup"]["tool"] == "dedup"
    assert rows["sql"]["tool"] == "query_sql"
    assert rows["tui"]["tool"] == "" and rows["tui"]["note"]


def test_parity_cli():
    from undatum.core import app

    result = CliRunner().invoke(app, ["mcp", "tools", "--parity", "--json"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)
    assert any(row["command"] == "rename" and row["tool"] == "rename" for row in rows)


def test_mcp_server_registers_generated_tools(data):
    pytest.importorskip("mcp")
    import asyncio

    from undatum.mcp.server import create_mcp_server

    server = create_mcp_server(root=str(data))
    tools = {tool.name: tool for tool in asyncio.run(server.list_tools())}
    assert {"dedup", "join", "rename"} <= set(tools)
    dedup = tools["dedup"]
    # mcp 1.x names it inputSchema, 2.x input_schema.
    schema = getattr(dedup, "input_schema", None) or dedup.inputSchema
    assert schema["properties"]["keep"]
