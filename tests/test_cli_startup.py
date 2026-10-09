"""CLI startup budget, quiet logging and lazily loaded plugin commands."""

import os
import statistics
import subprocess
import sys
import time

import pytest
from typer.testing import CliRunner

from undatum import core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEAVY_MODULES = ("pandas", "duckdb", "pyarrow", "matplotlib", "fastapi")


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def test_core_import_does_not_load_heavy_libraries():
    code = "import sys, undatum.core; print(','.join(sorted(sys.modules)))"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=_env(), check=True
    )
    loaded = set(result.stdout.strip().split(","))
    assert not [name for name in HEAVY_MODULES if name in loaded]


@pytest.mark.skipif(os.environ.get("CI") != "true", reason="timing is only enforced in CI")
def test_version_is_fast():
    timings = []
    for _ in range(5):
        start = time.perf_counter()
        subprocess.run(
            [sys.executable, "-m", "undatum", "--version"],
            check=False,
            capture_output=True,
            env=_env(),
        )
        timings.append(time.perf_counter() - start)
    # Interpreter start-up is part of the measurement; the budget leaves room for it.
    assert statistics.median(timings) <= 0.3


def test_successful_command_is_silent_on_stderr(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("a,b\n1,2\n3,4\n", encoding="utf8")
    result = subprocess.run(
        [sys.executable, "-m", "undatum", "count", str(source)],
        check=False,
        capture_output=True,
        text=True,
        env=_env(),
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "2"
    assert result.stderr == ""


def test_debug_flag_prints_diagnostics(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("a\n1\n", encoding="utf8")
    result = subprocess.run(
        [sys.executable, "-m", "undatum", "-vv", "count", str(source)],
        check=False,
        capture_output=True,
        text=True,
        env=_env(),
    )
    assert result.returncode == 0
    assert "DEBUG" in result.stderr


class _FakeEntryPoint:
    def __init__(self, name, loader):
        self.name = name
        self._loader = loader

    def load(self):
        return self._loader()


def test_plugin_command_is_loaded_on_demand(monkeypatch):
    calls = []

    def hello(name: str = "world"):
        """Say hello."""
        print(f"hello {name}")

    def loader():
        calls.append("loaded")
        return hello

    monkeypatch.setattr(
        core, "_plugin_command_entry_points", lambda: {"hello": _FakeEntryPoint("hello", loader)}
    )
    runner = CliRunner()
    result = runner.invoke(core.app, ["hello", "--name", "plugins"])
    assert result.exit_code == 0, result.output
    assert "hello plugins" in result.stdout
    assert calls == ["loaded"]


def test_broken_plugin_does_not_block_other_commands(monkeypatch, tmp_path):
    def loader():
        raise ImportError("plugin is broken")

    monkeypatch.setattr(
        core, "_plugin_command_entry_points", lambda: {"broken": _FakeEntryPoint("broken", loader)}
    )
    source = tmp_path / "data.csv"
    source.write_text("a\n1\n", encoding="utf8")
    runner = CliRunner()
    assert runner.invoke(core.app, ["count", str(source)]).exit_code == 0
    assert runner.invoke(core.app, ["broken"]).exit_code != 0
