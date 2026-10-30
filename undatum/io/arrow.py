"""Records as Arrow tables, for DuckDB to describe or write without pandas."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..common.errors import DependencyError, UndatumError


def records_table(records: Iterable[dict[str, Any]], *, mixed_as_text: bool = False) -> Any:
    """A ``pyarrow.Table`` of dict ``records``, one column per field in first-seen order.

    A field missing from a record is null; Arrow infers each column's type from its values
    (integers with missing values stay integers, nested objects become structs).

    Args:
        records: Records (dicts).
        mixed_as_text: Hold a field whose values have no common Arrow type (an integer and a
            string) as text, as DuckDB types such a pandas column; otherwise raise.

    Returns:
        ``pyarrow.Table``.

    Raises:
        UndatumError: A field's values have no common Arrow type, without ``mixed_as_text``.
    """
    import pyarrow as pa

    rows = list(records)
    columns = {}
    for name in dict.fromkeys(key for row in rows for key in row):
        values = [row.get(name) for row in rows]
        try:
            column = pa.array(values)
        except (pa.ArrowInvalid, pa.ArrowTypeError, pa.ArrowNotImplementedError) as exc:
            if not mixed_as_text:
                raise UndatumError(
                    f"Field '{name}' has values Arrow cannot hold in one column: {exc}",
                    context={"field": name},
                ) from exc
            column = pa.array([None if v is None else str(v) for v in values], pa.string())
        columns[name if isinstance(name, str) else str(name)] = column
    return pa.table(columns)


def import_pandas(feature: str, extra: str = "pandas") -> Any:
    """The pandas module, imported on use (pandas is an optional extra).

    Args:
        feature: What needs pandas, for the error message.
        extra: The undatum extra that installs pandas.

    Raises:
        DependencyError: pandas is not installed.
    """
    try:
        import pandas
    except ImportError:
        raise DependencyError(
            "pandas", feature=feature, install_command=f'pip install "undatum[{extra}]"'
        ) from None
    return pandas
