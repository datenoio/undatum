"""Filesystem sandbox for agent-facing tools (MCP server and LangChain tools).

Agents act on instructions that may come from the data they read, so every path an
agent passes to a tool must stay inside a configured root directory. The MCP server
and :func:`undatum.tools.langchain.get_tools` configure the sandbox (default: the
current working directory); direct Python calls to :mod:`undatum.tools` are not
restricted unless :func:`configure_sandbox` is called.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Tool arguments that name files.
PATH_ARGUMENTS = ("path", "input_path", "output_path", "source", "target")


class SandboxViolation(Exception):
    """A tool argument points outside the sandbox root."""

    def __init__(self, argument: str, value: str, root: Path, reason: str = "outside"):
        self.argument = argument
        self.value = value
        self.root = root
        self.code = "path_outside_root" if reason == "outside" else "remote_uri_not_allowed"
        if reason == "outside":
            message = f"'{argument}' must be inside the sandbox root {root}: {value}"
        else:
            message = (
                f"'{argument}' is a remote URI, which agent tools may not open: {value}. "
                "Start the server with --allow-anywhere to permit it."
            )
        super().__init__(message)


@dataclass(frozen=True)
class ToolSandbox:
    """Sandbox settings: ``root`` confines local paths; ``None`` means unrestricted."""

    root: Path | None

    @property
    def restricted(self) -> bool:
        return self.root is not None

    def resolve(self, argument: str, value: str) -> str:
        """Return ``value`` as an absolute path inside the root or raise SandboxViolation."""
        if self.root is None:
            return value
        if "://" in value:
            raise SandboxViolation(argument, value, self.root, reason="remote")
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.root / candidate
        # resolve() follows symlinks, so a link inside the root that points outside is rejected.
        resolved = candidate.resolve()
        if resolved != self.root and self.root not in resolved.parents:
            raise SandboxViolation(argument, value, self.root)
        return str(resolved)


_SANDBOX = ToolSandbox(root=None)


def configure_sandbox(root: str | os.PathLike[str] | None = None, allow_anywhere: bool = False):
    """Confine agent tools to ``root`` (default: the current directory).

    Args:
        root: Directory that tool paths must stay within.
        allow_anywhere: Disable the sandbox (trusted local use only).

    Returns:
        The active :class:`ToolSandbox`.
    """
    global _SANDBOX
    if allow_anywhere:
        _SANDBOX = ToolSandbox(root=None)
    else:
        base = Path(root) if root is not None else Path.cwd()
        _SANDBOX = ToolSandbox(root=base.resolve())
    return _SANDBOX


def current_sandbox() -> ToolSandbox:
    """Return the active sandbox."""
    return _SANDBOX


def check_tool_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate path arguments against the active sandbox.

    Returns:
        A copy of ``arguments`` with local paths resolved inside the root.

    Raises:
        SandboxViolation: If a path argument leaves the sandbox.
    """
    sandbox = _SANDBOX
    if not sandbox.restricted:
        return arguments
    checked = dict(arguments)
    for name, value in arguments.items():
        if name in PATH_ARGUMENTS or name.endswith("_path"):
            if isinstance(value, str) and value:
                checked[name] = sandbox.resolve(name, value)
        elif name.endswith("_paths") and isinstance(value, (list, tuple)):
            checked[name] = [
                sandbox.resolve(name, item) if isinstance(item, str) and item else item
                for item in value
            ]
    return checked


def restrict_duckdb(conn: Any) -> None:
    """Limit a DuckDB connection to files inside the sandbox root.

    Disables external access except for the root directory and locks the
    configuration so a query cannot re-enable it. No-op when unrestricted.
    """
    sandbox = _SANDBOX
    if not sandbox.restricted:
        return
    root = str(sandbox.root).replace("'", "''")
    conn.execute(f"SET allowed_directories = ['{root}{os.sep}']")
    conn.execute("SET enable_external_access = false")
    conn.execute("SET lock_configuration = true")
