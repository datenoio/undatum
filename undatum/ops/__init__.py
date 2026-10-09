"""Typed, streaming data operations shared by the CLI, the SDK and agent tools.

Example:
    >>> from undatum.io import open_source
    >>> from undatum.ops import RenameConfig, run
    >>> run("rename", RenameConfig(mapping={"a": "x"}), open_source("data.csv"), "out.parquet")
"""

from .base import REGISTRY, Operation, Streaming, register
from .expr import WhereConfig
from .query import JoinConfig, MaskConfig, SampleConfig, SelectConfig, SortConfig
from .rows import (
    FillConfig,
    HeadConfig,
    RenameConfig,
    ReplaceConfig,
    SearchConfig,
    SliceConfig,
)
from .runner import compose_sql, get_operation, run, run_steps, write_query, write_rows
from .structure import (
    CatConfig,
    DedupConfig,
    EnumConfig,
    ExcludeConfig,
    ExplodeConfig,
    FixLengthsConfig,
    ReverseConfig,
    TailConfig,
    TransposeConfig,
)

__all__ = [
    "CatConfig",
    "DedupConfig",
    "EnumConfig",
    "ExcludeConfig",
    "ExplodeConfig",
    "FillConfig",
    "FixLengthsConfig",
    "HeadConfig",
    "JoinConfig",
    "MaskConfig",
    "Operation",
    "REGISTRY",
    "RenameConfig",
    "ReplaceConfig",
    "ReverseConfig",
    "SampleConfig",
    "SearchConfig",
    "SelectConfig",
    "SliceConfig",
    "SortConfig",
    "Streaming",
    "TailConfig",
    "TransposeConfig",
    "WhereConfig",
    "compose_sql",
    "get_operation",
    "register",
    "run",
    "run_steps",
    "write_query",
    "write_rows",
]
