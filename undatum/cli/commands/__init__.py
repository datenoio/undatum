"""Top-level data commands of the undatum CLI, grouped by area.

Each module registers its commands on :data:`data_app`; ``undatum.core`` merges them into
the main app. Commands keep the order below in ``--help``.
"""

from . import (  # noqa: F401 - registers the commands
    combine,
    convert,
    describe,
    explore,
    fields,
    maintenance,
    quality,
    query,
    records,
)
from ._app import data_app

ORDER = [
    "convert",
    "repack",
    "extract",
    "uniq",
    "headers",
    "stats",
    "profile",
    "flatten",
    "frequency",
    "select",
    "split",
    "validate",
    "apply",
    "scheme",
    "analyze",
    "doc",
    "document",
    "schema",
    "schema_bulk",
    "ingest",
    "count",
    "head",
    "tail",
    "mask",
    "enum",
    "reverse",
    "table",
    "fixlengths",
    "sort",
    "sample",
    "search",
    "dedup",
    "fill",
    "rename",
    "explode",
    "replace",
    "cat",
    "join",
    "diff",
    "exclude",
    "transpose",
    "sniff",
    "slice",
    "plot",
    "fmt",
    "sql",
    "migrate-script",
    "schema-drift",
    "quality",
]

data_app.registered_commands.sort(
    key=lambda info: ORDER.index(info.name or info.callback.__name__)  # type: ignore[union-attr]
)

__all__ = ["data_app"]
