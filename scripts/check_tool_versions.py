"""Fail when the ruff version drifts between pyproject.toml, pre-commit and CI.

Usage:
    python scripts/check_tool_versions.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf8")
    precommit = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf8")
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf8")

    pinned = re.search(r'"ruff==([0-9.]+)"', pyproject)
    hook = re.search(r"ruff-pre-commit\s*\n\s*rev:\s*v([0-9.]+)", precommit)
    workflow = set(re.findall(r"ruff==([0-9.]+)", ci))
    if not pinned or not hook:
        print("ruff pin not found in pyproject.toml or .pre-commit-config.yaml")
        return 1
    versions = {"pyproject.toml": pinned.group(1), ".pre-commit-config.yaml": hook.group(1)}
    for version in workflow:
        versions[f"ci.yml ({version})"] = version
    if len(set(versions.values())) != 1:
        for source, version in versions.items():
            print(f"{source}: ruff {version}")
        return 1
    print(f"ruff {pinned.group(1)} everywhere")
    return 0


if __name__ == "__main__":
    sys.exit(main())
