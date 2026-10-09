"""Check that `undatum ...` command lines in OpenSpec scenarios use real options.

Usage:
    python scripts/check_spec_commands.py [paths...]

Scans Markdown files (default: openspec/specs and openspec/changes, excluding the
archive) for backticked `undatum ...` command lines and reports options that the
current CLI does not accept. Exit code 1 when problems are found.
"""

from __future__ import annotations

import logging
import pathlib
import re
import shlex
import sys

logging.disable(logging.CRITICAL)

import typer.main  # noqa: E402

from undatum.core import app  # noqa: E402

COMMAND_RE = re.compile(r"`([^`]*\bundatum [^`]+)`")
FENCE_RE = re.compile(r"^\s*```(\w*)")
# Shell operators that end one command (pipes, lists) or start a redirect.
COMMAND_SEPARATORS = {"|", "||", "&&", ";", "&"}
REDIRECTS = {">", ">>", "<", "2>", "&>"}


def _undatum_commands(line: str) -> list[list[str]]:
    """Split a shell line into the argument lists of its ``undatum`` commands."""
    lexer = shlex.shlex(line, posix=True, punctuation_chars=";&|<>")
    lexer.whitespace_split = True
    commands, current = [], []
    for token in lexer:
        if token in COMMAND_SEPARATORS:
            commands.append(current)
            current = []
        else:
            current.append(token)
    commands.append(current)
    result = []
    for tokens in commands:
        if tokens and tokens[0] == "undatum":
            cut = next((i for i, t in enumerate(tokens) if t in REDIRECTS), len(tokens))
            result.append(tokens[1:cut])
    return result


def _command_tree():
    root = typer.main.get_command(app)
    commands = {}

    def walk(cmd, prefix):
        # list_commands/get_command go through the root group, which applies the
        # CLI naming conventions (canonical names, short flags, aliases).
        if hasattr(cmd, "commands"):
            for name in cmd.list_commands(None):
                walk(cmd.get_command(None, name), prefix + [name])
        else:
            opts = set()
            for param in cmd.params:
                if param.param_type_name == "option":
                    opts.update(param.opts)
                    opts.update(param.secondary_opts)
            commands[" ".join(prefix)] = (opts, getattr(cmd, "_undatum_aliases", {}))

    walk(root, [])
    return commands


def check(paths: list[pathlib.Path]) -> list[str]:
    commands = _command_tree()
    problems = []
    for path in paths:
        in_shell_block = False
        for lineno, line in enumerate(path.read_text(encoding="utf8").splitlines(), start=1):
            fence = FENCE_RE.match(line)
            if fence:
                in_shell_block = not in_shell_block and fence.group(1) in ("bash", "sh", "shell")
                continue
            candidates = [m.group(1) for m in COMMAND_RE.finditer(line)]
            stripped = line.strip()
            if in_shell_block and "undatum " in stripped and not stripped.startswith("#"):
                candidates.append(stripped.split(" #", 1)[0].rstrip("\\").strip())
            for candidate in candidates:
                if "…" in candidate or "..." in candidate:
                    continue  # elided example, not a runnable command
                try:
                    commands_in_line = _undatum_commands(candidate)
                except ValueError:
                    continue
                for tokens in commands_in_line:
                    problems.extend(_check_tokens(commands, tokens, path, lineno))
    return problems


def _check_tokens(commands, tokens: list[str], path, lineno: int) -> list[str]:
    """Report unknown commands and options in one ``undatum`` argument list."""
    # Options before the first word belong to the root command (-v, -q).
    while tokens and tokens[0].startswith("-"):
        tokens = tokens[1:]
    # Two-word spellings the CLI rewrites (``schema drift`` -> ``schema-drift``).
    from undatum.core import _SPELLINGS

    if len(tokens) > 1 and (tokens[0], tokens[1]) in _SPELLINGS:
        tokens = _SPELLINGS[(tokens[0], tokens[1])] + tokens[2:]
    words = [t for t in tokens if not t.startswith("-")]
    name = next(
        (" ".join(words[:size]) for size in (3, 2, 1) if " ".join(words[:size]) in commands),
        None,
    )
    if name is None:
        if words and words[0] not in {"<command>"} and len(words) > 1:
            return [f"{path}:{lineno}: unknown command in `undatum {' '.join(tokens)}`"]
        return []
    problems = []
    from undatum.cli.conventions import DEPRECATED_COMMANDS

    if name in DEPRECATED_COMMANDS:
        problems.append(
            f"{path}:{lineno}: deprecated command `undatum {name}`"
            f" (use `undatum {DEPRECATED_COMMANDS[name]}`)"
        )
    options, aliases = commands[name]
    for token in tokens:
        if not token.startswith("-") or token == "-":
            continue
        option = token.split("=", 1)[0]
        if option in aliases:
            problems.append(
                f"{path}:{lineno}: deprecated option {option} in `undatum {name}`"
                f" (use {aliases[option]})"
            )
        elif option not in options and option not in {"--help"}:
            problems.append(f"{path}:{lineno}: `undatum {name}` has no option {option}")
    return problems


def main(argv: list[str]) -> int:
    if argv:
        paths = [pathlib.Path(p) for p in argv]
    else:
        paths = [p for p in pathlib.Path("openspec").rglob("*.md") if "archive" not in p.parts]
    files = []
    for path in paths:
        files.extend(sorted(path.rglob("*.md")) if path.is_dir() else [path])
    problems = check(files)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
