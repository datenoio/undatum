#!/usr/bin/env python3
"""Generate the rule reference of ``docs/docs/commands/validate-rules.md`` from the catalogue.

Usage::

    python scripts/generate_rule_reference.py           # write
    python scripts/generate_rule_reference.py --check   # exit 1 when the page is stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from undatum.validate.library import KEY_RULES, RULES  # noqa: E402

PAGE = ROOT / "docs" / "docs" / "commands" / "validate-rules.md"
BEGIN = "<!-- BEGIN GENERATED: rules -->"
END = "<!-- END GENERATED: rules -->"


def _cell(text: str) -> str:
    return (
        text.replace("|", "\\|").replace("{", "&#123;").replace("}", "&#125;").replace("<", "&lt;")
    )


def render_block() -> str:
    """The generated tables: formats and rule keys."""
    lines = [
        BEGIN,
        "",
        "### Formats (`format: NAME`)",
        "",
        "| Name | Valid values | Parameters |",
        "|------|--------------|------------|",
    ]
    for spec in RULES.values():
        params = "<br/>".join(f"`{name}`: {_cell(text)}" for name, text in spec.params.items())
        if spec.extra:
            params += (
                "<br/>" if params else ""
            ) + f"needs `undatum[{spec.extra}]` for all features"
        lines.append(f"| `{spec.name}` | {_cell(spec.description)} | {params} |")
    lines += ["", "### Rule keys", "", "| Key | Checks |", "|-----|--------|"]
    for key, text in KEY_RULES.items():
        names = " / ".join(f"`{k.strip()}`" for k in key.split("/"))
        lines.append(f"| {names} | {_cell(text)} |")
    lines += ["", END]
    return "\n".join(lines)


def apply_block(text: str, block: str) -> str:
    """Replace the generated block of ``text``."""
    start = text.index(BEGIN)
    end = text.index(END) + len(END)
    return text[:start] + block + text[end:]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when the page is stale")
    args = parser.parse_args(argv)
    current = PAGE.read_text(encoding="utf8")
    updated = apply_block(current, render_block())
    if args.check:
        if updated != current:
            print(f"stale: {PAGE.relative_to(ROOT)}")
            return 1
        return 0
    if updated != current:
        PAGE.write_text(updated, encoding="utf8")
        print(f"Updated {PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
