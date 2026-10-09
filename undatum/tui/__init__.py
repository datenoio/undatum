"""Optional interactive TUI for dataset exploration.

Importing this package does not require Textual. Widget modules under
``undatum.tui.app`` and ``undatum.tui.screens`` do.
"""

from .session import DEFAULT_SAMPLE_LIMIT, MAX_SAMPLE_LIMIT, SessionState


def __getattr__(name):
    # ``TuiServices`` pulls in iterabledata and DuckDB; import it only when used so
    # ``undatum --help`` stays fast.
    if name == "TuiServices":
        from .services import TuiServices

        return TuiServices
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DEFAULT_SAMPLE_LIMIT",
    "MAX_SAMPLE_LIMIT",
    "SessionState",
    "TuiServices",
]
