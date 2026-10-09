"""
undatum: a command-line tool for data processing. Brings CSV simplicity to JSON lines and BSON

"""

__version__ = "1.8.0"
__author__ = "Ivan Begtin"
__licence__ = "MIT"

__all__ = ["Dataset", "QueryResult", "StatsResult"]


def __getattr__(name):
    # Lazy import so `import undatum` stays lightweight for CLI startup
    if name == "Dataset":
        from .sdk.dataset import Dataset

        return Dataset
    if name in {"StatsResult", "QueryResult"}:
        from .sdk.results import QueryResult, StatsResult

        return StatsResult if name == "StatsResult" else QueryResult
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
