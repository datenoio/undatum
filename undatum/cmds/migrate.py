"""Rewrite scripts that call undatum to the canonical CLI spellings.

Deprecated option spellings (``--filetype``, ``--outtype``, ``--n``, ...), the engine value
``iterable`` and the hidden duplicate commands (``profile``, ``document``, ``scheme``) keep
working until 2.0. :func:`migrate_text` rewrites ``undatum`` invocations in shell scripts,
Makefiles, CI files and documentation, and the ``command:`` / ``engine:`` keys of pipeline
YAML. Changes it cannot make mechanically (``ingest`` to ``db load``, options a replacement
command does not have) are reported as findings.

Text that shows old spellings on purpose (a migration table, the page of a deprecated
command) opts out with a ``migrate-script: ignore`` marker in a ``#`` or HTML comment; see
:func:`ignored_lines`.

The alias tables come from the live command tree (``undatum.cli.conventions``), so the
rewrite always matches what the CLI itself accepts.
"""

from __future__ import annotations

import difflib
import os
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

# Files scanned when a directory is given.
SCRIPT_SUFFIXES = (".sh", ".bash", ".zsh", ".yml", ".yaml", ".md", ".mk", ".txt", ".cfg", ".toml")
SCRIPT_NAMES = ("Makefile", "Dockerfile", "Justfile")
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "build", "dist", ".tox"}

GLOBAL_FLAGS = {"-v", "-vv", "-vvv", "--verbose", "-q", "--quiet"}
GROUPS = {
    "ai",
    "api",
    "config",
    "db",
    "examples",
    "formats",
    "mcp",
    "package",
    "pipeline",
    "plugins",
}
# Hidden duplicate commands that are a plain rename.
RENAMED_COMMANDS = {"profile": "stats", "document": "doc"}
# ``scheme`` options with no ``schema`` counterpart.
SCHEME_UNSUPPORTED = {"--delimiter", "-d", "--encoding", "--format-in", "-F", "--zipfile"}
# What ``scheme`` did without --stype; appended after the last argument of the call.
SCHEME_DEFAULT_FORMAT = " --format cerberus"
_BREAKS = {"|", "||", "&&", ";", "&", "(", ")", "`"}
# A redirection such as ``>``, ``2>`` or ``>out.yaml``; group 1 is an attached target.
_REDIRECT = re.compile(r"^[0-9]*[<>]+(.*)$")

# Opt-out markers: a line holding only the comment, or (``ignore``) a comment ending a line.
_DIRECTIVE = r"migrate-script:\s*(ignore|ignore-start|ignore-end)"
_MARKER_LINE = re.compile(rf"^\s*(?:<!--\s*{_DIRECTIVE}\s*-->|#\s*{_DIRECTIVE})\s*$")
_MARKER_END_OF_LINE = re.compile(
    r"\s(?:<!--\s*migrate-script:\s*ignore\s*-->|#\s*migrate-script:\s*ignore)\s*$"
)
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


@dataclass
class Finding:
    """A change that needs a person: the line and what to do."""

    path: str
    line: int
    message: str


@dataclass
class Migration:
    """Result of migrating one file."""

    path: str
    original: str
    migrated: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        """Whether the text was rewritten."""
        return self.original != self.migrated

    def diff(self) -> str:
        """Unified diff of the rewrite (empty when nothing changed)."""
        return "".join(
            difflib.unified_diff(
                self.original.splitlines(keepends=True),
                self.migrated.splitlines(keepends=True),
                fromfile=f"a/{self.path}",
                tofile=f"b/{self.path}",
            )
        )


_ALIASES: dict[str, dict[str, str]] | None = None


def command_aliases() -> dict[str, dict[str, str]]:
    """Deprecated option spelling -> canonical spelling, per command path."""
    global _ALIASES
    if _ALIASES is None:
        import typer.main

        from ..core import app

        root = typer.main.get_command(app)
        ctx = root.make_context("undatum", [], resilient_parsing=True)
        tables: dict[str, dict[str, str]] = {}

        def walk(command: object, path: str) -> None:
            children = getattr(command, "commands", None)
            if children is not None:
                for name, child in children.items():
                    walk(child, f"{path} {name}")
            else:
                tables[path] = dict(getattr(command, "_undatum_aliases", {}))

        for name in root.list_commands(ctx):  # type: ignore[attr-defined]
            command = root.get_command(ctx, name)  # type: ignore[attr-defined]
            if command is not None:
                walk(command, name)
        _ALIASES = tables
    return _ALIASES


def _tokens(line: str) -> Iterator[tuple[int, int, str, bool]]:
    """Shell-like tokens of a line: ``(start, end, text, quoted)``; stops at a comment."""
    i, n = 0, len(line)
    while i < n:
        char = line[i]
        if char.isspace():
            i += 1
            continue
        if char == "#" and (i == 0 or line[i - 1].isspace()):
            return
        if line.startswith(("&&", "||"), i):
            yield i, i + 2, line[i : i + 2], False
            i += 2
            continue
        if char in "|;&()`":
            yield i, i + 1, char, False
            i += 1
            continue
        start, quoted = i, False
        while i < n and not line[i].isspace() and line[i] not in "|;&()`":
            if line[i] in "'\"":
                quote, quoted = line[i], True
                i += 1
                while i < n and line[i] != quote:
                    i += 2 if line[i] == "\\" and quote == '"' else 1
                i += 1
            else:
                i += 2 if line[i] == "\\" else 1
        yield start, min(i, n), line[start : min(i, n)], quoted


@dataclass
class _Invocation:
    """State of one ``undatum ...`` invocation while its tokens are read."""

    stage: str = "globals"  # globals -> command -> subcommand -> args
    path: str = ""
    aliases: dict[str, str] = field(default_factory=dict)
    scheme: bool = False
    scheme_format: bool = False
    # (line number, offset) after the last argument of a ``scheme`` call.
    scheme_end: tuple[int, int] | None = None
    redirect_target_next: bool = False
    engine_value_next: bool = False


def _starts_invocation(text: str) -> bool:
    return text == "undatum" or text.endswith("/undatum")


# Words that may precede a command: ``sudo``, ``python -m``, ``uv run``, a ``$`` prompt,
# environment assignments and YAML keys such as ``run:``.
_PREFIX_WORDS = {"sudo", "time", "exec", "nohup", "env", "xargs", "command", "uv", "pipx", "run"}
_PREFIX_WORDS |= {"poetry", "pdm", "hatch", "-m", "$", "-", ">", "!"}
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PYTHON = re.compile(r"^(?:.*/)?python[0-9.]*$")


def _keeps_command_position(text: str) -> bool:
    return (
        text in _PREFIX_WORDS
        or text.endswith(":")
        or bool(_ASSIGNMENT.match(text))
        or bool(_PYTHON.match(text))
    )


def migrate_text(text: str, path: str = "<text>") -> Migration:
    """Rewrite deprecated undatum spellings in ``text``.

    Args:
        text: File contents.
        path: Name used in findings and diffs; ``.yml`` / ``.yaml`` also enable the
            pipeline rewrites.

    Returns:
        The migration (original and rewritten text, findings).
    """
    aliases = command_aliases()
    yaml_file = path.lower().endswith((".yml", ".yaml"))
    lines = text.splitlines(keepends=True)
    skip = ignored_lines(lines)
    findings: list[Finding] = []
    bodies: list[str] = []
    # Edits per line, applied at the end: a ``scheme`` call can end lines after it started.
    edits: dict[int, list[tuple[int, int, str]]] = {}
    state: _Invocation | None = None
    for number, line in enumerate(lines, start=1):
        if number in skip:
            _end_invocation(state, edits)
            state = None
            bodies.append(line)
            continue
        command_position = state is None
        body = line.rstrip("\r\n")
        newline = line[len(body) :]
        if yaml_file:
            body = _migrate_yaml_line(body, path, number, findings)
        bodies.append(body + newline)
        continues = body.rstrip().endswith("\\")
        for start, end, token, quoted in _tokens(body):
            if not quoted and token in _BREAKS:
                _end_invocation(state, edits)
                state, command_position = None, True
                continue
            if state is None:
                if command_position and not quoted and _starts_invocation(token):
                    state = _Invocation()
                elif not (command_position and not quoted and _keeps_command_position(token)):
                    command_position = False
                continue
            edit = _migrate_token(state, start, end, token, quoted, aliases, path, number, findings)
            if edit:
                edits.setdefault(number, []).append(edit)
        if not continues:
            _end_invocation(state, edits)
            state = None
    _end_invocation(state, edits)
    out = []
    for number, line in enumerate(bodies, start=1):
        for start, end, replacement in sorted(edits.get(number, ()), reverse=True):
            line = line[:start] + replacement + line[end:]
        out.append(line)
    return Migration(path, text, "".join(out), findings)


def _end_invocation(
    state: _Invocation | None, edits: dict[int, list[tuple[int, int, str]]]
) -> None:
    """Finish a call: ``scheme`` without --stype gets the old default after its arguments."""
    if state is not None and state.scheme and not state.scheme_format and state.scheme_end:
        number, offset = state.scheme_end
        edits.setdefault(number, []).append((offset, offset, SCHEME_DEFAULT_FORMAT))


def ignored_lines(lines: list[str]) -> set[int]:
    """Line numbers (from 1) that opt-out markers leave alone, the markers included.

    A marker is ``migrate-script: ignore`` (or ``ignore-start`` / ``ignore-end``) in an HTML
    comment (``<!-- ... -->``) or a ``#`` comment:

    - ``ignore`` on a line of its own skips the next block: a fenced code block up to its
      closing fence, otherwise the lines up to the next blank line (a table, a paragraph,
      a group of commands);
    - ``ignore`` at the end of a line skips that line;
    - ``ignore-start`` and ``ignore-end`` on lines of their own skip everything between
      them (to the end of the file without an ``ignore-end``).

    Args:
        lines: The lines of a file.

    Returns:
        The numbers of the lines to keep as they are.
    """
    skip: set[int] = set()
    index, total = 0, len(lines)

    def skip_through(last: Callable[[str], object]) -> None:
        """Skip lines up to and including the first one ``last`` accepts."""
        nonlocal index
        while index < total:
            skip.add(index + 1)
            index += 1
            if last(lines[index - 1]):
                return

    while index < total:
        line = lines[index]
        index += 1
        directive = _marker(line)
        if directive is None:
            if _MARKER_END_OF_LINE.search(line):
                skip.add(index)
            continue
        skip.add(index)
        if directive == "ignore-start":
            skip_through(lambda text: _marker(text) == "ignore-end")
        elif directive == "ignore":
            while index < total and not lines[index].strip():
                index += 1
            fence = _FENCE.match(lines[index]) if index < total else None
            if fence:
                char, width = re.escape(fence.group(1)[0]), len(fence.group(1))
                closing = re.compile(rf"^ {{0,3}}{char}{{{width},}}\s*$")
                skip.add(index + 1)
                index += 1
                skip_through(closing.match)
            else:
                while index < total and lines[index].strip():
                    skip.add(index + 1)
                    index += 1
    return skip


def _marker(line: str) -> str | None:
    """The directive of a line that holds only an opt-out marker comment."""
    match = _MARKER_LINE.match(line)
    return (match.group(1) or match.group(2)) if match else None


def _migrate_token(
    state: _Invocation,
    start: int,
    end: int,
    token: str,
    quoted: bool,
    aliases: dict[str, dict[str, str]],
    path: str,
    line: int,
    findings: list[Finding],
) -> tuple[int, int, str] | None:
    """The edit for one token of an invocation (``None``: keep it)."""
    if state.stage == "globals":
        if token in GLOBAL_FLAGS or token.startswith("-v"):
            return None
        if token.startswith("-") or quoted:
            state.stage = "args"
            return None
        if token in GROUPS:
            state.path, state.stage = token, "subcommand"
            return None
        state.stage = "args"
        if token in RENAMED_COMMANDS:
            state.path = RENAMED_COMMANDS[token]
            state.aliases = aliases.get(state.path, {})
            return start, end, state.path
        if token == "scheme":
            state.path, state.scheme = "schema", True
            state.aliases = aliases.get("schema", {})
            state.scheme_end = (line, end)
            return start, end, "schema"
        if token == "ingest":
            findings.append(
                Finding(
                    path,
                    line,
                    "'ingest' is deprecated: use 'undatum db load FILE --db URI --table NAME' "
                    "(see the migration guide; the database goes into the URI)",
                )
            )
        state.path = token
        state.aliases = aliases.get(token, {})
        return None
    if state.stage == "subcommand":
        state.stage = "args"
        if not token.startswith("-") and not quoted:
            state.path = f"{state.path} {token}"
            state.aliases = aliases.get(state.path, {})
        return None
    # Arguments.
    if state.scheme and token != "\\":
        # The default format goes after the arguments (FILE first), before redirections.
        redirect = _REDIRECT.match(token)
        if state.redirect_target_next:
            state.redirect_target_next = False
        elif redirect:
            state.redirect_target_next = not redirect.group(1)
        else:
            state.scheme_end = (line, end)
    if quoted:
        state.engine_value_next = False
        return None
    if state.engine_value_next:
        state.engine_value_next = False
        if token == "iterable":
            return start, end, "python"
        return None
    name, sep, value = token.partition("=")
    if name in ("--engine", "-e"):
        if sep and value == "iterable":
            return start, end, f"{name}=python"
        state.engine_value_next = not sep
        return None
    if state.scheme:
        if name in SCHEME_UNSUPPORTED:
            findings.append(
                Finding(path, line, f"'schema' has no {name} option (was accepted by 'scheme')")
            )
        if name == "--stype":
            # --stype chose the format, so the default is not appended.
            state.scheme_format = True
            return start, end, "--format" + (sep + value if sep else "")
    if name in state.aliases:
        return start, end, state.aliases[name] + (sep + value if sep else "")
    return None


_YAML_COMMAND = re.compile(r"^(\s*(?:-\s+)?command:\s*)([\"']?)([a-z-]+)\2(\s*(?:#.*)?)$")
_YAML_ENGINE = re.compile(r"^(\s*(?:-\s+)?engine:\s*)([\"']?)iterable\2(\s*(?:#.*)?)$")


def _migrate_yaml_line(body: str, path: str, line: int, findings: list[Finding]) -> str:
    """Pipeline YAML: ``command: profile`` -> ``stats``, ``engine: iterable`` -> ``python``."""
    match = _YAML_COMMAND.match(body)
    if match:
        command = match.group(3)
        if command in RENAMED_COMMANDS:
            quote = match.group(2)
            new = RENAMED_COMMANDS[command]
            return f"{match.group(1)}{quote}{new}{quote}{match.group(4)}"
        if command in ("scheme", "ingest"):
            target = (
                "command: schema with args format: cerberus"
                if command == "scheme"
                else "command: db load with args input, db (URI with the database), table"
            )
            findings.append(Finding(path, line, f"pipeline step '{command}': use {target}"))
        return body
    match = _YAML_ENGINE.match(body)
    if match:
        quote = match.group(2)
        return f"{match.group(1)}{quote}python{quote}{match.group(3)}"
    return body


def iter_script_files(paths: list[str]) -> Iterator[Path]:
    """The given files, plus script-like files under the given directories."""
    for given in paths:
        root = Path(given)
        if root.is_file():
            yield root
            continue
        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for name in sorted(filenames):
                if name.endswith(SCRIPT_SUFFIXES) or name in SCRIPT_NAMES:
                    yield Path(directory) / name


def migrate_files(paths: list[str]) -> list[Migration]:
    """Migrations of every script file under ``paths`` (files are not changed)."""
    results = []
    for file in iter_script_files(paths):
        try:
            text = file.read_text(encoding="utf8")
        except (UnicodeDecodeError, OSError):
            continue
        if "undatum" not in text and not str(file).endswith((".yml", ".yaml")):
            continue
        results.append(migrate_text(text, str(file)))
    return results


def write_migration(migration: Migration) -> None:
    """Write a rewritten file in place (atomically)."""
    target = Path(migration.path)
    temp = target.with_name(f".{target.name}.undatum-migrate")
    temp.write_text(migration.migrated, encoding="utf8")
    os.replace(temp, target)
