#!/usr/bin/env python3
"""Render the Homebrew formula for a released version from PyPI metadata.

Usage::

    python scripts/render_homebrew_formula.py 1.8.0 > Formula/undatum.rb
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path
from typing import Any

TEMPLATE = Path(__file__).resolve().parent.parent / "packaging" / "homebrew" / "undatum.rb.in"


def sdist(metadata: dict[str, Any]) -> tuple[str, str]:
    """``(url, sha256)`` of the source distribution in PyPI JSON metadata."""
    for item in metadata["urls"]:
        if item["packagetype"] == "sdist":
            return item["url"], item["digests"]["sha256"]
    raise SystemExit("the release has no source distribution on PyPI")


def render(version: str, url: str, sha256: str, template: str | None = None) -> str:
    """The formula text."""
    text = template if template is not None else TEMPLATE.read_text(encoding="utf8")
    return (
        text.replace("{{VERSION}}", version).replace("{{URL}}", url).replace("{{SHA256}}", sha256)
    )


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    version = argv[0].removeprefix("v")
    with urllib.request.urlopen(f"https://pypi.org/pypi/undatum/{version}/json") as response:
        metadata = json.load(response)
    url, sha256 = sdist(metadata)
    sys.stdout.write(render(version, url, sha256))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
