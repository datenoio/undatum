"""DOCX table extraction (used by ``analyze`` for Word documents)."""

try:
    from docx import Document
    from docx.oxml.simpletypes import ST_Merge
    from docx.table import _Cell
except ImportError:  # pragma: no cover - optional dependency
    Document = None
    ST_Merge = None
    _Cell = None


def _extract_table(table, strip_space=False):
    """Return the cell values of ``table`` row by row, repeating merged cells."""
    results = []
    for tr in table._tbl.tr_lst:
        row = []
        for tc in tr.tc_lst:
            for grid_span_idx in range(tc.grid_span):
                if tc.vMerge == ST_Merge.CONTINUE:
                    value = results[-1][len(row) - 1]
                elif grid_span_idx > 0:
                    value = row[-1]
                else:
                    value = _Cell(tc, table).text.replace("\n", " ")
                if strip_space:
                    value = value.strip()
                row.append(value)
        results.append(row)
    return results


def extract_docx_tables(filename, strip_space=True):
    """Extract every table of a ``.docx`` file.

    Args:
        filename: Path to the Word document.
        strip_space: Strip leading and trailing whitespace from cell values.

    Returns:
        A list of dicts with ``id``, ``num_cols``, ``num_rows``, ``style`` and ``data``
        (rows of cell values).

    Raises:
        RuntimeError: If python-docx is not installed.
    """
    if Document is None:
        raise RuntimeError("python-docx is required for DOCX processing")
    tables = []
    document = Document(filename)
    for n, table in enumerate(document.tables, start=1):
        tables.append(
            {
                "id": n,
                "num_cols": len(table.columns),
                "num_rows": len(table.rows),
                "style": table.style.name,
                "data": _extract_table(table, strip_space=strip_space),
            }
        )
    return tables


def analyze_docx(filename, extract_data=None, strip_space=True):
    """Describe the tables of a ``.docx`` file (see :func:`extract_docx_tables`).

    ``extract_data`` is accepted for compatibility and ignored: data is always included.
    """
    return extract_docx_tables(filename, strip_space=strip_space)
