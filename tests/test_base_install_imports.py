"""Base-install import tests.

The published 1.7.0 wheel crashed on ``undatum --version`` because a module
imported at startup pulled in ``starlette`` from the optional ``api`` extra.
These tests run the CLI in a subprocess where every package that only ships
with an extra is made unimportable, so the suite catches that class of bug
even when the dev environment has all extras installed.
"""

import os
import subprocess
import sys
import textwrap

import pytest

# Top-level packages that are only installed through optional extras.
EXTRA_ONLY_PACKAGES = [
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


def _run(code: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.dirname(os.path.dirname(os.path.abspath(__file__)))]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])
    )
    return subprocess.run(
        [sys.executable, "-c", BLOCKER + textwrap.dedent(code)],
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
