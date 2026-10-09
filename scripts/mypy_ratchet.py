"""Type-check ratchet: mypy errors per file may only go down.

Usage:
    python scripts/mypy_ratchet.py            # run mypy and compare with the baseline
    python scripts/mypy_ratchet.py --update   # rewrite the baseline after fixing errors
    python scripts/mypy_ratchet.py --update --allow-moves   # after moving code between files

The baseline (``mypy-baseline.json``) maps each file to its number of mypy errors.
The check fails when a file has more errors than recorded, or when a file that is not
in the baseline has any. Files that improved are reported so the baseline can be
tightened with ``--update``; ``--update`` refuses to record an increase, unless
``--allow-moves`` is given and the total number of errors did not grow (code moved from one
file to others).

mypy reads its configuration from ``pyproject.toml``; run this with the minimum
supported Python version (3.10), as CI does.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "mypy-baseline.json"
ERROR_LINE = re.compile(r"^(?P<file>[^:\s]+\.py):\d+: error: ")


def run_mypy(target: str = "undatum") -> tuple[Counter[str], str]:
    """Run mypy on ``target`` and return error counts per file plus the raw output."""
    result = subprocess.run(
        [sys.executable, "-m", "mypy", target],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    if result.returncode not in (0, 1) or "errors prevented further checking" in output:
        raise RuntimeError(f"mypy did not complete:\n{output}")
    counts: Counter[str] = Counter()
    for line in output.splitlines():
        match = ERROR_LINE.match(line)
        if match:
            counts[match.group("file")] += 1
    return counts, output


def compare(current: Counter[str], baseline: dict[str, int]) -> tuple[list[str], list[str]]:
    """Return ``(regressions, improvements)`` as human-readable lines."""
    regressions, improvements = [], []
    for path in sorted(set(current) | set(baseline)):
        now, before = current.get(path, 0), baseline.get(path, 0)
        if now > before:
            regressions.append(f"{path}: {before} -> {now} errors")
        elif now < before:
            improvements.append(f"{path}: {before} -> {now} errors")
    return regressions, improvements


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    parser.add_argument(
        "--allow-moves",
        action="store_true",
        help="with --update: accept per-file increases when the total does not grow",
    )
    args = parser.parse_args(argv)

    current, output = run_mypy()
    baseline = json.loads(BASELINE.read_text(encoding="utf8")) if BASELINE.exists() else {}
    regressions, improvements = compare(current, baseline)

    if args.update:
        moved = args.allow_moves and sum(current.values()) <= sum(baseline.values())
        if regressions and baseline and not moved:
            print("Refusing to record new type errors:", *regressions, sep="\n  ")
            if sum(current.values()) <= sum(baseline.values()):
                print("If the code only moved between files, add --allow-moves.")
            return 1
        BASELINE.write_text(
            json.dumps(dict(sorted(current.items())), indent=2) + "\n", encoding="utf8"
        )
        print(f"Baseline updated: {sum(current.values())} errors in {len(current)} files")
        return 0

    total, recorded = sum(current.values()), sum(baseline.values())
    print(f"mypy: {total} errors (baseline {recorded})")
    if improvements:
        print("Fewer errors than the baseline; run with --update to lock them in:")
        print(*improvements, sep="\n  ")
    if regressions:
        print("New type errors:", *regressions, sep="\n  ")
        for line in output.splitlines():
            match = ERROR_LINE.match(line)
            if match and any(r.startswith(match.group("file") + ":") for r in regressions):
                print(line)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
