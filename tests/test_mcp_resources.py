"""MCP resources and prompts, through a real client session (mcp 1.x and 2.x)."""

from __future__ import annotations

import asyncio
import contextlib
import json

import pytest

pytest.importorskip("mcp")

from undatum.mcp.resources import PROMPTS, list_datasets, render_prompt  # noqa: E402
from undatum.tools.sandbox import configure_sandbox  # noqa: E402


@pytest.fixture
def root(tmp_path):
    (tmp_path / "data.csv").write_text("id,city\n1,Berlin\n2,\n3,Paris\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "events.jsonl").write_text('{"a": 1}\n{"a": 2}\n')
    (tmp_path / "notes.txt").write_text("not data")
    (tmp_path / "secret.csv").write_text("x\n1\n")
    yield tmp_path
    configure_sandbox(allow_anywhere=True)


@contextlib.asynccontextmanager
async def _client(server):
    try:  # mcp 2.x
        from mcp.client import Client

        async with Client(server) as client:
            yield client
    except ImportError:  # mcp 1.x
        from mcp.shared.memory import create_connected_server_and_client_session

        async with create_connected_server_and_client_session(server._mcp_server) as client:
            yield client


def _text(result) -> str:
    return result.contents[0].text


def _run(root, coroutine):
    from undatum.mcp.server import create_mcp_server

    server = create_mcp_server(root=str(root))

    async def main():
        async with _client(server) as client:
            return await coroutine(client)

    return asyncio.run(main())


def test_dataset_listing(root):
    async def check(client):
        uris = {str(r.uri) for r in (await client.list_resources()).resources}
        assert {"undatum://datasets", "undatum://formats"} <= uris
        listing = json.loads(_text(await client.read_resource("undatum://datasets")))
        return listing

    listing = _run(root, check)
    paths = [d["path"] for d in listing["datasets"]]
    assert paths == ["data.csv", "secret.csv", "sub/events.jsonl"]
    entry = listing["datasets"][2]
    assert (
        entry["format"] == "jsonl"
        and entry["sample"] == "undatum://dataset/sub%2Fevents.jsonl/sample"
    )


def test_schema_and_sample(root):
    async def check(client):
        listed = await client.list_resource_templates()
        # mcp 2.x uses snake_case attribute names.
        templates = getattr(listed, "resource_templates", None) or listed.resourceTemplates
        uris = {getattr(t, "uri_template", None) or t.uriTemplate for t in templates}
        assert {"undatum://dataset/{path}/schema", "undatum://dataset/{path}/sample"} <= uris
        schema = json.loads(_text(await client.read_resource("undatum://dataset/data.csv/schema")))
        sample = json.loads(
            _text(await client.read_resource("undatum://dataset/sub%2Fevents.jsonl/sample"))
        )
        return schema, sample

    schema, sample = _run(root, check)
    assert schema["fields"] == [
        {"name": "id", "type": "integer", "nullable": False},
        {"name": "city", "type": "string", "nullable": True},
    ]
    assert sample["records"] == [{"a": 1}, {"a": 2}]


def test_paths_outside_the_root_are_refused(root):
    async def check(client):
        with pytest.raises(Exception):  # noqa: B017 - the error type differs between mcp versions
            await client.read_resource("undatum://dataset/..%2F..%2Fetc%2Fpasswd/sample")
        return True

    assert _run(root, check)


def test_prompts(root):
    async def check(client):
        names = {p.name for p in (await client.list_prompts()).prompts}
        prompt = await client.get_prompt(
            "plan-conversion", {"path": "sub/events.jsonl", "target_format": "csv"}
        )
        return names, prompt.messages[0].content.text

    names, text = _run(root, check)
    assert names >= set(PROMPTS)
    assert "`sub/events.jsonl`" in text and ".csv" in text
    assert "undatum://dataset/sub%2Fevents.jsonl/schema" in text


def test_rule_prompt_lists_the_catalogue():
    text = render_prompt("draft-validation-rules", "data.csv")
    for rule in ("country", "iban", "date"):
        assert rule in text


def test_listing_is_bounded(tmp_path, monkeypatch):
    from undatum.mcp import resources

    for i in range(5):
        (tmp_path / f"f{i}.csv").write_text("a\n1\n")
    configure_sandbox(tmp_path)
    monkeypatch.setattr(resources, "MAX_DATASETS", 3)
    try:
        listing = list_datasets()
    finally:
        configure_sandbox(allow_anywhere=True)
    assert len(listing["datasets"]) == 3 and listing["truncated"] is True
