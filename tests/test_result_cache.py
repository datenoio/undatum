"""Cached results of informational commands: same output, and never for a changed file."""

from __future__ import annotations

import json
import logging
import os

import pytest
from typer.testing import CliRunner

from undatum.common import cache
from undatum.common.app_config import clear_cli_defaults_cache
from undatum.core import app

runner = CliRunner()
pytestmark = pytest.mark.result_cache

CSV = "id,name,city\n1,Alice,Berlin\n2,Bob,Paris\n3,Carol,Berlin\n"


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv(cache.DIR_ENV, str(tmp_path / "cache"))
    monkeypatch.delenv("UNDATUM_CACHE", raising=False)
    monkeypatch.chdir(tmp_path)
    clear_cli_defaults_cache()
    (tmp_path / "data.csv").write_text(CSV, encoding="utf8")
    _age(tmp_path / "data.csv")
    yield tmp_path
    clear_cli_defaults_cache()


def _age(path, seconds=60):
    """Files modified in the last two seconds are not cached."""
    then = os.stat(path).st_mtime_ns - seconds * 10**9
    os.utime(path, ns=(then, then))


def _run(*args):
    result = runner.invoke(app, list(args))
    assert result.exit_code == 0, result.output
    return result.stdout


def _hit(caplog, *args):
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="undatum.common.cache"):
        output = _run(*args)
    return output, any("using the cached result" in m for m in caplog.messages)


COMMANDS = [
    ["count"],
    ["headers"],
    ["sniff"],
    ["schema"],
    ["schema", "--format", "odcs"],
    ["analyze"],
    ["stats", "--engine", "python"],
]


@pytest.mark.parametrize("command", COMMANDS, ids=[" ".join(c) for c in COMMANDS])
@pytest.mark.parametrize("json_output", [False, True], ids=["text", "json"])
def test_cached_output_equals_computed(data, caplog, command, json_output):
    args = [command[0], "data.csv", *command[1:], *(["--json"] if json_output else [])]
    if command[1:2] == ["--format"] and json_output:
        pytest.skip("--format odcs prints YAML")
    computed = _run(*args, "--no-cache")
    first, first_hit = _hit(caplog, *args)
    second, second_hit = _hit(caplog, *args)
    if command[0] == "schema" and "--format" in command:
        computed, first, second = (
            "\n".join(line for line in text.splitlines() if not line.startswith("id: "))
            for text in (computed, first, second)
        )  # a new contract id each time
    assert (first_hit, second_hit) == (False, True)
    assert first == computed and second == computed


def test_changed_file_is_read_again(data, caplog):
    assert _run("count", "data.csv").strip() == "3"
    with open("data.csv", "a", encoding="utf8") as handle:
        handle.write("4,Dave,Rome\n")
    _age(data / "data.csv", 30)
    output, hit = _hit(caplog, "count", "data.csv")
    assert (output.strip(), hit) == ("4", False)
    # Same size, new modification time
    (data / "data.csv").write_text(CSV.replace("Alice", "Alicx"), encoding="utf8")
    os.utime(data / "data.csv", ns=(10**18, 10**18))
    _run("headers", "data.csv")
    os.utime(data / "data.csv", ns=(2 * 10**18, 2 * 10**18))
    assert _hit(caplog, "headers", "data.csv")[1] is False


def test_options_are_part_of_the_key(data, caplog):
    assert _run("count", "data.csv").strip() == "3"
    output, hit = _hit(caplog, "count", "data.csv", "--where", "city = 'Berlin'")
    assert (output.strip(), hit) == ("2", False)
    assert _hit(caplog, "count", "data.csv", "--where", "city = 'Berlin'") == ("2\n", True)
    assert _hit(caplog, "count", "data.csv", "--json")[1] is True  # presentation only


def test_path_as_given(data, caplog):
    _run("count", "data.csv", "--json")
    output, hit = _hit(caplog, "count", "./data.csv", "--json")
    assert hit is False and json.loads(output)["file"] == "./data.csv"


@pytest.mark.use_cli_config
@pytest.mark.parametrize("how", ["flag", "env", "config"])
def test_turned_off(data, monkeypatch, how):
    args = ["count", "data.csv"]
    if how == "flag":
        args.append("--no-cache")
    elif how == "env":
        monkeypatch.setenv("UNDATUM_CACHE", "0")
    else:
        (data / "undatum.yaml").write_text("defaults:\n  cache: false\n", encoding="utf8")
    clear_cli_defaults_cache()
    _run(*args)
    assert not (data / "cache").exists()


def test_library_calls_do_not_cache(data):
    from undatum import Dataset

    assert Dataset.read(str(data / "data.csv")).count() == 3
    assert Dataset.read(str(data / "data.csv")).stats()["count"] == 3
    assert not (data / "cache").exists()


def test_unusable_cache_does_not_fail(data, caplog, monkeypatch):
    (data / "blocked").write_text("a file, not a directory", encoding="utf8")
    monkeypatch.setenv(cache.DIR_ENV, str(data / "blocked" / "cache"))
    assert _run("count", "data.csv").strip() == "3"
    monkeypatch.setenv(cache.DIR_ENV, str(data / "cache"))
    _run("count", "data.csv")
    for entry in (data / "cache").glob("*/count-*.json"):
        entry.write_text("{not json", encoding="utf8")
    output, hit = _hit(caplog, "count", "data.csv")
    assert (output.strip(), hit) == ("3", False)


def test_recently_modified_files_are_not_cached(data, caplog):
    (data / "new.csv").write_text(CSV, encoding="utf8")
    _run("count", "new.csv")
    assert _hit(caplog, "count", "new.csv")[1] is False
    _age(data / "new.csv")
    _run("count", "new.csv")
    assert _hit(caplog, "count", "new.csv")[1] is True


def test_not_cached_inputs_and_changing_files(data):
    options = {"cache": True}
    assert cache.cached("count", "-", options, lambda: 1) == 1
    assert cache.cached("count", "s3://bucket/data.csv", options, lambda: 2) == 2
    assert cache.cached("count", str(data), options, lambda: 3) == 3

    def grows():
        with open(data / "data.csv", "a", encoding="utf8") as handle:
            handle.write("9,Zed,Oslo\n")
        return 4

    assert cache.cached("count", str(data / "data.csv"), options, grows) == 4
    assert not (data / "cache").exists()


def test_list_and_clear(data):
    (data / "other.csv").write_text(CSV, encoding="utf8")
    _age(data / "other.csv")
    _run("count", "data.csv")
    _run("headers", "data.csv")
    _run("count", "other.csv")
    listed = json.loads(_run("cache", "list", "--json"))
    assert listed["schema"] == "undatum.cache/1"
    by_path = {os.path.basename(entry["path"]): entry for entry in listed["entries"]}
    assert sorted(r["command"] for r in by_path["data.csv"]["results"]) == ["count", "headers"]
    assert not any(entry["stale"] for entry in listed["entries"])

    (data / "other.csv").unlink()
    assert "Removed the results of 1 files" in _run("cache", "clear", "--stale")
    remaining = json.loads(_run("cache", "list", "--json"))["entries"]
    assert [os.path.basename(entry["path"]) for entry in remaining] == ["data.csv"]
    _run("cache", "clear")
    assert json.loads(_run("cache", "list", "--json"))["entries"] == []
    assert "No cached results" in _run("cache", "list")
