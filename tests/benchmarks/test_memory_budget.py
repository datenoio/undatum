"""Peak memory of row-wise commands stays bounded and does not grow with the input.

Builds 250k- and 1M-row CSV files (about 45 MB), so it only runs when
``UNDATUM_MEMORY_TESTS=1`` is set (the CI ``memory-budget`` job does). Budget from the
``refactor-streaming-operations-core`` spec: at most 300 MB peak RSS for 1M rows, and less
than 20% growth from 250k to 1M rows. Growth below 40 MB is allowed whatever the share: DuckDB
buffers grow a little with the file, and the DuckDB paths start at about 80 MB.
"""

from __future__ import annotations

import csv
import os
import subprocess
import sys

import pytest

pytestmark = [
    pytest.mark.memory,
    pytest.mark.skipif(
        os.environ.get("UNDATUM_MEMORY_TESTS") != "1",
        reason="set UNDATUM_MEMORY_TESTS=1 to run the memory budget tests",
    ),
]

BUDGET_MB = 300
MAX_GROWTH = 0.20
GROWTH_FLOOR_MB = 40
PEAK = (
    "import resource, subprocess, sys\n"
    "subprocess.run(sys.argv[1:], check=True, stdout=subprocess.DEVNULL)\n"
    "peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss\n"
    "print(peak / 1048576 if sys.platform == 'darwin' else peak / 1024)\n"
)
COMMANDS = {
    "rename": ["rename", "--map", "a:x"],
    "fill": ["fill", "--fields", "b", "--value", "z"],
    "replace": ["replace", "--field", "b", "--pattern", "name", "--replacement", "n"],
    "search": ["search", "--pattern", "name1", "--fields", "b"],
    "explode": ["explode", "--field", "d", "--separator", "x"],
    "enum": ["enum"],
    "head": ["head", "-n", "5"],
    "tail": ["tail", "-n", "5"],
    "reverse": ["reverse"],
    "dedup": ["dedup", "--key-fields", "a"],
}


@pytest.fixture(scope="module")
def inputs(tmp_path_factory):
    directory = tmp_path_factory.mktemp("memory")
    paths = {}
    for rows in (250_000, 1_000_000):
        path = directory / f"rows_{rows}.csv"
        with open(path, "w", newline="", encoding="utf8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["a", "b", "c", "d", "e"])
            for i in range(rows):
                writer.writerow([i, f"name{i % 1000}", i * 0.5, "x" * 10, i % 7])
        paths[rows] = path
    return paths


def peak_mb(args: list[str]) -> float:
    result = subprocess.run(
        [sys.executable, "-c", PEAK, sys.executable, "-m", "undatum", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


@pytest.mark.parametrize("engine", ["python", "duckdb"])
@pytest.mark.parametrize("name", sorted(COMMANDS))
def test_peak_memory_is_bounded(inputs, tmp_path, name, engine):
    command = COMMANDS[name]
    if engine == "duckdb" and name not in ("rename", "fill", "replace", "search", "head"):
        pytest.skip("Python-only operation")
    peaks = {}
    for rows, path in inputs.items():
        out = tmp_path / f"out_{rows}.csv"
        args = [*command, str(path), "--output", str(out)]
        if name in ("rename", "fill", "replace", "search", "head"):
            args += ["--engine", engine]
        peaks[rows] = peak_mb(args)
    small, large = peaks[250_000], peaks[1_000_000]
    assert large <= BUDGET_MB, f"{name}: {large:.0f} MB for 1M rows"
    allowed = max(small * MAX_GROWTH, GROWTH_FLOOR_MB)
    assert large - small <= allowed, f"{name}: {small:.0f} -> {large:.0f} MB"
