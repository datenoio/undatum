#!/usr/bin/env python3
"""Publish the JSON result layouts of informational commands.

Writes one JSON Schema per layout of ``undatum.common.results.SCHEMAS`` to
``docs/static/schemas/`` and the key tables of ``docs/docs/commands/json-output.md``
(between the generated markers).

Usage::

    python scripts/generate_result_schemas.py           # write
    python scripts/generate_result_schemas.py --check   # exit 1 when something is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from undatum.common.results import SCHEMAS, schema_file  # noqa: E402

SCHEMA_DIR = ROOT / "docs" / "static" / "schemas"
PAGE = ROOT / "docs" / "docs" / "commands" / "json-output.md"
BEGIN = "<!-- BEGIN GENERATED: result-schemas -->"
END = "<!-- END GENERATED: result-schemas -->"


def render_schemas() -> dict[Path, str]:
    """Schema file path -> JSON text."""
    return {
        SCHEMA_DIR / schema_file(schema.id): json.dumps(schema.json_schema(), indent=2) + "\n"
        for schema in SCHEMAS.values()
    }


def render_block() -> str:
    """The generated part of the documentation page."""
    lines = [BEGIN, ""]
    for schema in SCHEMAS.values():
        url = f"pathname:///schemas/{schema_file(schema.id)}"
        lines += [
            f"### `{schema.id}`",
            "",
            f"{schema.title}. Printed by `undatum {schema.command} --json`. [JSON Schema]({url})",
            "",
            "| Key | Type | Always | Description |",
            "|-----|------|--------|-------------|",
            f"| `schema` | string | yes | `{schema.id}` |",
        ]
        for key, (kind, description) in schema.properties.items():
            always = "yes" if key in schema.required else ""
            kind_text = kind.replace("|", " or ")
            lines.append(f"| `{key}` | {kind_text} | {always} | {description} |")
        lines.append("")
    lines.append(END)
    return "\n".join(lines)


def apply_block(text: str, block: str) -> str:
    """Replace the generated block of ``text`` (or append it)."""
    if BEGIN in text and END in text:
        start = text.index(BEGIN)
        end = text.index(END) + len(END)
        return text[:start] + block + text[end:]
    return text.rstrip("\n") + "\n\n" + block + "\n"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when output is stale")
    args = parser.parse_args(argv)

    outputs = render_schemas()
    page = PAGE.read_text(encoding="utf8")
    outputs[PAGE] = apply_block(page, render_block()).rstrip("\n") + "\n"
    stale = [
        path
        for path, text in outputs.items()
        if not path.exists() or path.read_text(encoding="utf8") != text
    ]
    extra = sorted(set(SCHEMA_DIR.glob("*.json")) - set(outputs)) if SCHEMA_DIR.exists() else []
    if args.check:
        for path in [*stale, *extra]:
            print(f"stale: {path.relative_to(ROOT)}")
        return 1 if stale or extra else 0
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for path in stale:
        path.write_text(outputs[path], encoding="utf8")
    for path in extra:
        path.unlink()
    print(f"Updated {len(stale)} files, removed {len(extra)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
