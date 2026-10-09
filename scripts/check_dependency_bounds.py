"""Check that every runtime dependency in pyproject.toml has version bounds.

Usage:
    python scripts/check_dependency_bounds.py [pyproject.toml]

Each entry of ``[project] dependencies`` and of every optional-dependency group except
``dev`` needs a lower bound (tested by the "lowest direct dependencies" CI job) and an
upper bound below the next major version. Exceptions:

- references to other extras (``undatum[...]``, ``iterabledata[...]``), whose packages
  are bounded where they are declared;
- calendar-versioned packages, where "next major" means next year (:data:`CALVER`);
- packages listed in :data:`NO_UPPER_BOUND` with the reason next to them.

Exit code 1 when an entry breaks the rule.
"""

from __future__ import annotations

import pathlib
import sys

from packaging.requirements import Requirement

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]

# Released as YYYY.M.x; there is no semantic major version to stay below.
CALVER = {"dask", "fsspec", "gcsfs", "adlfs", "s3fs"}
# pyarrow publishes a major version every few months without breaking the Parquet/ORC
# reader and writer API that undatum (through iterabledata) uses.
NO_UPPER_BOUND = {"pyarrow"}
# Groups that are not installed by users.
SKIPPED_GROUPS = {"dev"}
EXTRA_REFERENCES = {"undatum", "iterabledata"}

LOWER_OPS = {">=", ">", "==", "~=", "==="}
UPPER_OPS = {"<", "<=", "==", "~=", "==="}


def problems_for(requirement: str, group: str) -> list[str]:
    """Return the rule violations of one requirement string."""
    req = Requirement(requirement)
    name = req.name.lower()
    if req.extras and name in EXTRA_REFERENCES:
        return []
    operators = {spec.operator for spec in req.specifier}
    problems = []
    if not operators & LOWER_OPS:
        problems.append(f"[{group}] {requirement}: no lower bound")
    if name not in CALVER | NO_UPPER_BOUND and not operators & UPPER_OPS:
        problems.append(f"[{group}] {requirement}: no upper bound")
    return problems


def check(path: pathlib.Path) -> list[str]:
    """Return every violation in the pyproject file at ``path``."""
    project = tomllib.loads(path.read_text(encoding="utf8"))["project"]
    groups = {"dependencies": project.get("dependencies", [])}
    for group, requirements in project.get("optional-dependencies", {}).items():
        if group not in SKIPPED_GROUPS:
            groups[f"extra:{group}"] = requirements
    return [
        problem
        for group, requirements in groups.items()
        for requirement in requirements
        for problem in problems_for(requirement, group)
    ]


def main(argv: list[str]) -> int:
    path = pathlib.Path(argv[0] if argv else "pyproject.toml")
    problems = check(path)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} dependencies without bounds (see {__file__})", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
