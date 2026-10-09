"""CLI naming conventions: canonical names, short flags, deprecated aliases."""

import pytest
import typer.main
from typer.testing import CliRunner

from undatum.cli.conventions import AI_GROUP_RENAMES, DEPRECATED_COMMANDS, RENAMES
from undatum.core import app

runner = CliRunner(env={"COLUMNS": "200"})


def _leaf_commands():
    root = typer.main.get_command(app)
    leaves = []

    def walk(group, prefix):
        for name in group.list_commands(None):
            command = group.get_command(None, name)
            path = f"{prefix} {name}".strip()
            if hasattr(command, "commands"):
                walk(command, path)
            else:
                leaves.append((path, command))

    walk(root, "")
    return leaves


def test_no_command_shows_a_deprecated_option_name():
    deprecated = set(RENAMES)
    offenders = []
    for path, command in _leaf_commands():
        for param in command.params:
            if param.param_type_name != "option" or getattr(param, "hidden", False):
                continue
            visible = set(param.opts) | set(param.secondary_opts)
            if path.startswith("ai "):
                visible &= deprecated | set(AI_GROUP_RENAMES)
            else:
                visible &= deprecated
            if visible:
                offenders.append(f"{path}: {sorted(visible)}")
    assert offenders == []


def test_short_flags_are_unique_per_command():
    for path, command in _leaf_commands():
        seen = {}
        for param in command.params:
            for opt in (*getattr(param, "opts", []), *getattr(param, "secondary_opts", [])):
                if opt.startswith("-") and not opt.startswith("--"):
                    assert opt not in seen, f"{path}: {opt} used by {seen[opt]} and {param.name}"
                    seen[opt] = param.name


def test_deprecated_commands_are_hidden_from_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in DEPRECATED_COMMANDS:
        assert f" {name} " not in result.stdout


def test_old_option_name_still_works_with_warning(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("a\n2\n1\n", encoding="utf8")
    result = runner.invoke(app, ["sort", str(source), "--by", "a", "--filetype", "csv"])
    assert result.exit_code == 0, result.output
    assert "Option --filetype is deprecated; use --format-in" in result.stderr


def test_short_output_and_limit_flags(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("a\n1\n2\n3\n", encoding="utf8")
    out = tmp_path / "top.jsonl"
    result = runner.invoke(app, ["head", str(source), "-n", "2", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert len(out.read_text(encoding="utf8").splitlines()) == 2


@pytest.mark.parametrize("old,new", [("--n", "--limit")])
def test_head_limit_alias(tmp_path, old, new):
    source = tmp_path / "data.csv"
    source.write_text("a\n1\n2\n3\n", encoding="utf8")
    result = runner.invoke(app, ["head", str(source), old, "1"])
    assert result.exit_code == 0, result.output
    # CSV in, CSV out: header plus one row.
    assert result.stdout.strip().splitlines() == ["a", "1"]
    assert f"use {new}" in result.stderr


def test_deprecated_command_warns(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("a\n1\n", encoding="utf8")
    result = runner.invoke(app, ["profile", str(source)])
    assert "Command 'profile' is deprecated; use 'undatum stats'" in result.stderr
