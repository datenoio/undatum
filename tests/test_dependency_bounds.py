"""Runtime dependencies declare lower and upper version bounds."""

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _checker():
    spec = importlib.util.spec_from_file_location(
        "check_dependency_bounds", ROOT / "scripts" / "check_dependency_bounds.py"
    )
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except ModuleNotFoundError as exc:  # Python 3.10 without tomli
        pytest.skip(f"needs {exc.name}")
    return module


def test_pyproject_dependencies_are_bounded():
    assert _checker().check(ROOT / "pyproject.toml") == []


@pytest.mark.parametrize(
    "requirement,expected",
    [
        ("requests>=2.32,<3", []),
        ("requests", ["no lower bound", "no upper bound"]),
        ("requests>=2.32", ["no upper bound"]),
        ("requests<3", ["no lower bound"]),
        ("pyarrow>=16", []),
        ("fsspec>=2024.2", []),
        ("iterabledata[lakehouse]", []),
        ("undatum[api,mcp]", []),
        ("foo==1.2.3", []),
    ],
)
def test_bounds_rule(requirement, expected):
    problems = _checker().problems_for(requirement, "dependencies")
    assert [p.rsplit(": ", 1)[1] for p in problems] == expected
