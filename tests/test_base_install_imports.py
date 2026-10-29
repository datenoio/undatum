"""Base-install import tests.

The published 1.7.0 wheel crashed on ``undatum --version`` because a module
imported at startup pulled in ``starlette`` from the optional ``api`` extra.
These tests run the CLI in a subprocess where every package that only ships
with an extra is made unimportable, so the suite catches that class of bug
even when the dev environment has all extras installed.
"""

import json
import os
import subprocess
import sys
import textwrap

import pytest

# Top-level packages that are only installed through optional extras.
EXTRA_ONLY_PACKAGES = [
    "pandas",
    "fastapi",
    "starlette",
    "uvicorn",
    "httpx",
    "jinja2",
    "multipart",
    "textual",
    "matplotlib",
    "mcp",
    "langchain_core",
    "polars",
    "dask",
    "boto3",
    "fsspec",
    "s3fs",
    "gcsfs",
    "adlfs",
    "frictionless",
    "psycopg2",
    "pymysql",
    "pyodbc",
    "clickhouse_driver",
    "pdfplumber",
    "pdf2image",
    "pytesseract",
    "textract",
]

# Modules that exist only to serve an optional extra; importing them without
# that extra is expected to fail with ModuleNotFoundError.
EXTRA_ONLY_MODULES = (
    "undatum.cmds.api_app",
    "undatum.tui.app",
    "undatum.tui.screens.",
    "undatum.web.app",
    "undatum.mcp.server",
    "undatum.tools.langchain",
)

BLOCKER = textwrap.dedent(
    f"""
    import importlib.abc
    import sys

    BLOCKED = set({EXTRA_ONLY_PACKAGES!r})

    class _ExtraBlocker(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path=None, target=None):
            if fullname.split(".")[0] in BLOCKED:
                raise ModuleNotFoundError(f"No module named {{fullname!r}}", name=fullname)
            return None

    sys.meta_path.insert(0, _ExtraBlocker())
    for name in list(sys.modules):
        if name.split(".")[0] in BLOCKED:
            del sys.modules[name]
    """
)


def _run(code: str, *, block: tuple[str, ...] = ()) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    return subprocess.run(
        [
            sys.executable,
            "-c",
            BLOCKER + f"BLOCKED.update({list(block)!r})\n" + textwrap.dedent(code),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_cli_version_without_extras():
    result = _run(
        """
        import sys
        from undatum.__main__ import main
        sys.argv = ["undatum", "--version"]
        main()
        """
    )
    assert result.returncode == 0, result.stderr
    assert "undatum" in result.stdout


def test_all_core_modules_import_without_extras():
    result = _run(
        f"""
        import importlib
        import pkgutil
        import undatum

        extra_only = {EXTRA_ONLY_MODULES!r}
        failures = []
        for info in pkgutil.walk_packages(undatum.__path__, "undatum."):
            name = info.name
            try:
                importlib.import_module(name)
            except ModuleNotFoundError as exc:
                if not name.startswith(extra_only):
                    failures.append(f"{{name}}: {{exc}}")
            except Exception as exc:  # pragma: no cover - reported below
                failures.append(f"{{name}}: {{type(exc).__name__}}: {{exc}}")
        if failures:
            raise SystemExit("\\n".join(failures))
        """
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_mcp_tools_parity_without_click():
    # typer>=0.26 vendors click, and click only arrives through extras (uvicorn in ``api``),
    # so undatum code must not import it directly.
    result = _run(
        """
        import sys
        from undatum.__main__ import main
        sys.argv = ["undatum", "mcp", "tools", "--parity", "--json"]
        main()
        """,
        block=("click",),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    rows = {row["command"]: row for row in json.loads(result.stdout)}
    assert rows["dedup"]["tool"] == "dedup"


@pytest.mark.parametrize(
    "argv",
    [
        ["api", "openapi", "--config", "missing.yml"],
        ["tui", "missing.csv"],
        ["web", "missing.csv"],
    ],
)
def test_command_needing_missing_extra_exits_2(argv):
    result = _run(
        f"""
        import sys
        from undatum.__main__ import main
        sys.argv = ["undatum", *{argv!r}]
        main()
        """
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert "pip install" in (result.stdout + result.stderr)


FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


@pytest.mark.parametrize(
    "argv",
    [
        ["analyze", os.path.join(FIXTURES, "books.xml"), "--outtype", "json"],
        ["schema", os.path.join(FIXTURES, "books.jsonl"), "--flatten-nested"],
        ["schema", os.path.join(FIXTURES, "books.xml")],
    ],
)
def test_structure_of_records_without_pandas(argv):
    """Records undatum reads itself are described through Arrow, not pandas."""
    result = _run(
        f"""
        import sys
        from undatum.__main__ import main
        sys.argv = ["undatum", *{argv!r}]
        try:
            main()
        finally:
            assert "pandas" not in sys.modules
        """
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "title" in result.stdout


@pytest.mark.parametrize(
    "argv,extra",
    [
        (["analyze", os.path.join(FIXTURES, "books.xml"), "--use-pandas"], "pandas"),
        (["extract", os.path.join(FIXTURES, "2cols6rows.xlsx")], "extract"),
    ],
)
def test_commands_that_need_pandas_exit_2(argv, extra):
    result = _run(
        f"""
        import sys
        from undatum.__main__ import main
        sys.argv = ["undatum", *{argv!r}]
        main()
        """
    )
    assert result.returncode == 2, result.stdout + result.stderr
    assert f'pip install "undatum[{extra}]"' in result.stdout + result.stderr


def test_sdk_to_pandas_without_pandas():
    path = os.path.join(FIXTURES, "2cols6rows.csv")
    result = _run(
        f"""
        from undatum import Dataset
        from undatum.common.errors import DependencyError
        try:
            Dataset.read({path!r}).to_pandas()
        except DependencyError as exc:
            assert 'pip install "undatum[pandas]"' in str(exc), str(exc)
        else:
            raise AssertionError("to_pandas() worked without pandas")
        """
    )
    assert result.returncode == 0, result.stdout + result.stderr
