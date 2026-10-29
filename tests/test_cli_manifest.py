"""The CLI described as data: the manifest, the tool definitions and tool_argv()."""

from __future__ import annotations

import functools
import json
import re

import pytest
from typer.testing import CliRunner

from undatum.cli.manifest import (
    manifest,
    root_context,
    tool_argv,
    tool_name,
    walk,
)
from undatum.common.errors import EXIT_CODES, UndatumError
from undatum.common.results import COMMANDS
from undatum.core import app

runner = CliRunner()


@pytest.fixture(scope="module")
def document():
    return manifest()


@pytest.fixture(scope="module")
def commands(document):
    return {entry["name"]: entry for entry in document["commands"]}


_root = functools.cache(root_context)


def _leaves():
    root = _root()
    return {path: command for path, command, _ in walk(root.command, "", root)}


def test_every_command_is_described(commands):
    assert set(commands) == set(_leaves())
    assert {"count", "convert", "db query", "formats list", "commands"} <= set(commands)


def test_count_entry(commands):
    count = commands["count"]
    assert count["usage"] == "undatum count [OPTIONS] INPUT_FILE"
    assert count["arguments"][0]["name"] == "input_file"
    assert count["arguments"][0]["required"]
    options = {option["name"]: option for option in count["options"]}
    assert options["format_in"]["flags"] == ["--format-in", "-F"]
    assert options["format_in"]["deprecated_flags"] == ["--filetype"]
    assert options["table"]["flags"] == ["--table", "--sheet"]
    assert options["engine"]["choices"] == ["auto", "duckdb", "python"]
    assert options["start_page"] == {**options["start_page"], "type": "integer", "default": 0}
    assert options["json"]["flag"]
    assert count["engines"] == ["auto", "duckdb", "python"]
    assert count["capabilities"]["writes"] == "a number"
    assert count["results"] == [{"schema": "undatum.count/1", "when": None}]


def test_results_with_options(commands):
    assert {"schema": "undatum.validate/1", "when": "--rules"} in commands["validate"]["results"]
    assert commands["head"]["results"] == []


def test_examples_are_split_from_help(commands):
    entry = commands["extensions list"]
    assert entry["examples"][0] == "undatum extensions list"
    assert "Examples:" not in entry["help"]


def test_global_options_and_exit_codes(document):
    options = {option["name"]: option for option in document["global_options"]}
    assert options["verbose"]["count"] and options["verbose"]["flags"] == ["--verbose", "-v"]
    assert "install_completion" not in options
    assert document["exit_codes"] == {str(code): text for code, text in EXIT_CODES.items()}


def test_json_document():
    result = runner.invoke(app, ["commands", "--json"])
    assert result.exit_code == 0, result.output
    document = json.loads(result.stdout)
    assert document["schema"] == "undatum.commands/1"
    assert set(document) == {"schema", *COMMANDS.properties}
    assert any(group["name"] == "db" for group in document["groups"])


def test_group_and_search():
    names = [entry["name"] for entry in manifest(["db"])["commands"]]
    assert names and all(name.startswith("db ") for name in names)
    found = manifest(search="duplicate rows")
    assert [entry["name"] for entry in found["commands"]] == ["dedup"]
    assert found["groups"] == []


def test_unknown_command():
    result = runner.invoke(app, ["commands", "nope"])
    assert result.exit_code == 1
    assert "No command or group named 'nope'" in str(result.exception)


def test_text_listing():
    result = runner.invoke(app, ["commands", "--search", "duplicate"])
    assert result.exit_code == 0
    assert "dedup" in result.stdout
    assert "Remove duplicate rows." in result.stdout


def test_json_and_tools_conflict():
    assert runner.invoke(app, ["commands", "--json", "--tools"]).exit_code == 2


def test_tool_definitions(document):
    result = runner.invoke(app, ["commands", "--tools"])
    assert result.exit_code == 0, result.output
    tools = json.loads(result.stdout)
    assert len(tools) == len(document["commands"])
    names = [tool["name"] for tool in tools]
    assert len(set(names)) == len(names)
    for tool in tools:
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tool["name"]), tool["name"]
        parameters = tool["parameters"]
        assert parameters["type"] == "object"
        assert set(parameters["required"]) <= set(parameters["properties"])
    count = next(tool for tool in tools if tool["name"] == "undatum_count")
    assert count["parameters"]["required"] == ["input_file"]
    assert count["parameters"]["properties"]["engine"]["enum"] == ["auto", "duckdb", "python"]
    assert "undatum.count/1" in count["description"]
    jsonschema = pytest.importorskip("jsonschema")
    for tool in tools:
        jsonschema.Draft202012Validator.check_schema(tool["parameters"])


def _sample(param):
    """A value of the parameter's type that Click converts without callbacks."""
    if param.get("count"):
        return 2
    if param.get("flag"):
        return param["negation"] is None or param["default"] is not False
    if param["choices"]:
        value = param["choices"][-1]
    else:
        value = {"integer": 3, "number": 1.5, "boolean": True}.get(param["type"], "x")
    return [value, value] if param["multiple"] else value


def _parsed(path, argv):
    root = _root()
    command = root.command
    ctx = root
    for word in path.split():
        command = command.get_command(ctx, word)
        ctx = command.context_class(command, info_name=word, parent=ctx)
    words = len(path.split())
    return command, command.make_context(path, argv[words:], parent=root, resilient_parsing=True)


@pytest.mark.parametrize("path", sorted(_leaves()))
def test_tool_calls_round_trip(commands, path):
    entry = commands[path]
    params = [*entry["arguments"], *entry["options"]]
    call = {param["name"]: _sample(param) for param in params}
    argv = tool_argv(tool_name(path), call, [entry])
    command, ctx = _parsed(path, argv)
    by_flag = {flag: p for p in command.params for flag in getattr(p, "opts", [])}
    for param in params:
        click_param = (
            by_flag[param["flags"][0]]
            if "flags" in param
            else next(p for p in command.params if p.name == param["name"])
        )
        if not click_param.expose_value:
            continue  # handled by a callback (the shared --format-out of record commands)
        value = ctx.params[click_param.name]
        expected = call[param["name"]]
        if param.get("flag") and not expected and param["negation"] is None:
            continue  # a switch that is off is left out of the command line
        if isinstance(value, tuple):
            value = list(value)
        if param["type"] == "boolean" and not param.get("flag"):
            expected = [True, True] if param["multiple"] else True
        assert value == expected, (param["name"], argv)


def test_tool_argv_examples():
    assert tool_argv("undatum_count", {"input_file": "data.csv", "format_in": "csv"}) == [
        "count",
        "--format-in",
        "csv",
        "data.csv",
    ]
    assert tool_argv("db query", {"query": "SELECT 1"})[:2] == ["db", "query"]
    assert tool_argv("undatum_head", {"input_file": "-x.csv"})[-2:] == ["--", "-x.csv"]


def test_tool_argv_errors(commands):
    with pytest.raises(UndatumError, match="Unknown parameter"):
        tool_argv("undatum_count", {"input_file": "a.csv", "nope": 1}, [commands["count"]])
    with pytest.raises(UndatumError, match="Unknown undatum tool"):
        tool_argv("undatum_nope", {}, [commands["count"]])
