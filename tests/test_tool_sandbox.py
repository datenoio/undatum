"""Agent tool sandbox: paths stay inside the root, SQL is read-only."""

import os

import pytest

from undatum.tools import schemas
from undatum.tools.sandbox import configure_sandbox


@pytest.fixture
def sandbox(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    (root / "data.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf8")
    outside = tmp_path / "secret.csv"
    outside.write_text("token\nsupersecret\n", encoding="utf8")
    configure_sandbox(root)
    yield root, outside
    configure_sandbox(allow_anywhere=True)


def test_path_traversal_is_rejected(sandbox):
    root, outside = sandbox
    result = schemas.call_tool("read_sample", {"path": "../secret.csv"})
    assert result["ok"] is False
    assert result["code"] == "path_outside_root"


def test_absolute_path_outside_is_rejected(sandbox):
    root, outside = sandbox
    result = schemas.call_tool("query_sql", {"path": str(outside), "query": "SELECT * FROM data"})
    assert result["code"] == "path_outside_root"


def test_symlink_escape_is_rejected(sandbox):
    root, outside = sandbox
    link = root / "link.csv"
    os.symlink(outside, link)
    result = schemas.call_tool("read_sample", {"path": "link.csv"})
    assert result["code"] == "path_outside_root"


def test_remote_uri_is_rejected(sandbox):
    result = schemas.call_tool("read_sample", {"path": "s3://bucket/data.csv"})
    assert result["code"] == "remote_uri_not_allowed"


def test_relative_path_inside_root_works(sandbox):
    result = schemas.call_tool("query_sql", {"path": "data.csv", "query": "SELECT * FROM data"})
    assert result["ok"] is True, result
    assert result["data"]["count"] == 2


@pytest.mark.parametrize(
    "query",
    [
        "COPY (SELECT 1) TO '/tmp/undatum_sandbox_test.csv'",
        "SELECT 1; SELECT 2",
        "ATTACH 'other.db'",
        "INSTALL httpfs",
    ],
)
def test_non_select_statements_are_rejected(sandbox, query):
    result = schemas.call_tool("query_sql", {"path": "data.csv", "query": query})
    assert result["ok"] is False
    assert result["code"] == "read_only_query_required"
    assert not os.path.exists("/tmp/undatum_sandbox_test.csv")


def test_select_cannot_read_outside_root(sandbox):
    root, outside = sandbox
    result = schemas.call_tool(
        "query_sql", {"path": "data.csv", "query": f"SELECT * FROM read_text('{outside}')"}
    )
    assert result["ok"] is False
    assert "supersecret" not in str(result)


def test_unrestricted_when_allowed_anywhere(tmp_path):
    configure_sandbox(allow_anywhere=True)
    source = tmp_path / "x.csv"
    source.write_text("a\n1\n", encoding="utf8")
    result = schemas.call_tool("query_sql", {"path": str(source), "query": "SELECT * FROM data"})
    assert result["ok"] is True
