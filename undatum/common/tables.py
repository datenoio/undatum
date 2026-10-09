"""Plain-text tables for reports (Markdown pipe tables and ASCII grids)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rich.cells import cell_len


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _pad(text: str, width: int, right: bool) -> str:
    gap = " " * (width - cell_len(text))
    return gap + text if right else text + gap


def format_table(
    rows: Sequence[Sequence[Any]], headers: Sequence[str], style: str = "github"
) -> str:
    """Render ``rows`` as a text table.

    Columns whose values are all numbers are right-aligned; everything else is
    left-aligned. Widths account for wide (CJK) characters.

    Args:
        rows: Table rows; missing trailing cells are treated as empty.
        headers: Column titles.
        style: ``github`` for a Markdown pipe table (``|`` in values is escaped and
            newlines become spaces) or ``grid`` for an ASCII grid (newlines start a new
            line inside the cell).

    Returns:
        The table without a trailing newline.

    Raises:
        ValueError: If ``style`` is not supported.

    Example:
        >>> print(format_table([["a", 1]], ["Name", "Count"]))
        | Name | Count |
        |------|-------|
        | a    |     1 |
    """
    if style not in ("github", "grid"):
        raise ValueError(f"Unsupported table style: {style}")
    ncols = len(headers)
    padded = [list(row)[:ncols] + [None] * (ncols - len(row)) for row in rows]
    right = [
        any(row[i] is not None for row in padded)
        and all(_is_number(row[i]) for row in padded if row[i] is not None)
        for i in range(ncols)
    ]
    if style == "github":
        cells = [
            [_text(value).replace("|", "\\|").replace("\n", " ") for value in row] for row in padded
        ]
        widths = [
            max([cell_len(headers[i]), *(cell_len(row[i]) for row in cells)]) for i in range(ncols)
        ]
        lines = [
            "| " + " | ".join(_pad(h, widths[i], right[i]) for i, h in enumerate(headers)) + " |",
            "|" + "|".join("-" * (w + 2) for w in widths) + "|",
        ]
        lines.extend(
            "| " + " | ".join(_pad(c, widths[i], right[i]) for i, c in enumerate(row)) + " |"
            for row in cells
        )
        return "\n".join(lines)

    split = [[_text(value).split("\n") for value in row] for row in padded]
    widths = [
        max([cell_len(headers[i]), *(cell_len(line) for row in split for line in row[i])])
        for i in range(ncols)
    ]

    def border(char: str) -> str:
        return "+" + "+".join(char * (w + 2) for w in widths) + "+"

    def render(row_lines: list[list[str]], align: list[bool]) -> list[str]:
        height = max((len(cell) for cell in row_lines), default=1)
        out = []
        for n in range(height):
            parts = [
                _pad(cell[n] if n < len(cell) else "", widths[i], align[i])
                for i, cell in enumerate(row_lines)
            ]
            out.append("| " + " | ".join(parts) + " |")
        return out

    lines = [border("-"), *render([[h] for h in headers], [False] * ncols), border("=")]
    for row in split:
        lines.extend(render(row, right))
        lines.append(border("-"))
    if not split:
        lines[-1] = border("-")
    return "\n".join(lines)
