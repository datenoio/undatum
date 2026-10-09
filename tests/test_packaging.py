"""Release packaging: PyInstaller spec, Dockerfile, Homebrew formula template, conda recipe."""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = ROOT / "packaging" / "undatum.spec"

# conda-forge names of PyPI packages where they differ.
CONDA_NAMES = {"duckdb": "python-duckdb", "xxhash": "python-xxhash"}


def _render_module():
    spec = importlib.util.spec_from_file_location(
        "render_homebrew_formula", ROOT / "scripts" / "render_homebrew_formula.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_homebrew_formula_renders():
    module = _render_module()
    metadata = {
        "urls": [
            {"packagetype": "bdist_wheel", "url": "w", "digests": {"sha256": "x"}},
            {
                "packagetype": "sdist",
                "url": "https://files/undatum-1.8.0.tar.gz",
                "digests": {"sha256": "abc"},
            },
        ]
    }
    url, sha256 = module.sdist(metadata)
    formula = module.render("1.8.0", url, sha256)
    assert 'url "https://files/undatum-1.8.0.tar.gz"' in formula
    assert 'sha256 "abc"' in formula
    assert '"undatum==1.8.0"' in formula and "undatum 1.8.0" in formula
    assert "{{" not in formula


def _base_dependencies() -> dict[str, str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf8")
    block = text[text.index("dependencies = [") : text.index("]", text.index("dependencies = ["))]
    deps = {}
    # One requirement per line: '    "name>=1,<2",' (comment lines are skipped).
    for name, spec in re.findall(r'^\s+"([A-Za-z0-9_.-]+)([^"]*)",', block, re.M):
        deps[name.lower()] = spec.replace(" ", "")
    return deps


def test_conda_recipe_matches_pyproject():
    recipe = (ROOT / "packaging" / "conda" / "meta.yaml").read_text(encoding="utf8")
    run = recipe[recipe.index("  run:") : recipe.index("test:")]
    listed = {
        name: spec.replace(" ", "")
        for name, spec in re.findall(r"^\s+- ([A-Za-z0-9_.-]+) ?(.*)$", run, re.M)
    }
    for name, spec in _base_dependencies().items():
        conda_name = CONDA_NAMES.get(name, name)
        assert conda_name in listed, f"{conda_name} missing from the conda recipe"
        assert listed[conda_name] == spec, f"{conda_name}: {listed[conda_name]} != {spec}"
    version = re.search(r'__version__ = "([^"]+)"', (ROOT / "undatum" / "__init__.py").read_text())
    assert f'set version = "{version.group(1)}"' in recipe


def test_dockerfile_runs_as_non_root_user():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf8")
    assert re.search(r"^USER undatum$", dockerfile, re.M)
    assert 'ENTRYPOINT ["undatum"]' in dockerfile
    lines = (ROOT / ".dockerignore").read_text(encoding="utf8").splitlines()
    ignore = [line for line in lines if line and not line.startswith("#")]
    assert ignore[0] == "*" and "!undatum/" in ignore


def test_pyinstaller_spec_exists():
    assert SPEC_PATH.is_file()
    text = SPEC_PATH.read_text(encoding="utf-8")
    # The binary freezes a wrapper entry point that imports the package.
    assert "entry.py" in text
    assert "undatum.__main__" in text
    assert (ROOT / "packaging" / "entry.py").is_file()


def test_pyinstaller_spec_is_not_gitignored():
    tracked = subprocess.run(
        ["git", "ls-files", "--", "packaging/undatum.spec"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    if tracked.stdout.strip():
        return

    ignored = subprocess.run(
        [
            "git",
            "ls-files",
            "--others",
            "--ignored",
            "--exclude-standard",
            "--",
            "packaging/undatum.spec",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert not ignored.stdout.strip(), (
        "packaging/undatum.spec is gitignored; the release workflow cannot find it on tagged builds"
    )
