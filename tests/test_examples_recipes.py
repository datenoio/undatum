"""Recipe execution never passes substituted values through a shell."""

import sys
from unittest.mock import MagicMock, patch

from undatum.cmds.examples import RecipeManager, build_recipe_argv


def test_shell_metacharacters_stay_one_literal_argument():
    argv = build_recipe_argv(
        "undatum convert ${input} ${output}", {"input": "data.csv; rm -rf ~", "output": "out.jsonl"}
    )
    assert argv[-2:] == ["data.csv; rm -rf ~", "out.jsonl"]


def test_conditional_expansion_follows_shell_semantics():
    template = "undatum stats ${input} ${output_stats:+--output ${output_stats}}"
    assert build_recipe_argv(template, {"input": "a.csv", "output_stats": ""})[3:] == [
        "stats",
        "a.csv",
    ]
    assert build_recipe_argv(template, {"input": "a.csv", "output_stats": "s.json"})[3:] == [
        "stats",
        "a.csv",
        "--output",
        "s.json",
    ]


def test_undatum_runs_with_current_interpreter():
    argv = build_recipe_argv("undatum --version", {})
    assert argv[:3] == [sys.executable, "-m", "undatum"]


def test_recipe_runs_without_shell(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    completed = MagicMock(returncode=0)
    with patch("undatum.cmds.examples.subprocess.run", return_value=completed) as run:
        RecipeManager().run_recipe(
            "csv-to-jsonl", variables={"input": "in put.csv; echo pwned", "output": "o.jsonl"}
        )
    args, kwargs = run.call_args
    assert kwargs["shell"] is False
    assert args[0][-2:] == ["in put.csv; echo pwned", "o.jsonl"]
