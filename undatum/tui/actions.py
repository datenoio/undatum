"""Command-palette actions. This module must not import Textual."""

from __future__ import annotations

from dataclasses import dataclass

from .session import SessionState

DEFAULT_SQL_LIMIT = 500


@dataclass(frozen=True)
class TuiAction:
    """One palette row: title plus an equivalent CLI template."""

    id: str
    title: str
    cli_template: str
    handler: str
    slice: str = "c"


TUI_ACTIONS: tuple[TuiAction, ...] = (
    TuiAction("open", "Open another file", "undatum tui {source}", "open_file", "a"),
    TuiAction("help", "Show keybindings", "undatum tui --help", "help", "a"),
    TuiAction("profile", "Profile dataset", "undatum stats {source}", "profile", "b"),
    TuiAction(
        "frequency",
        "Frequency on selected field",
        "undatum frequency {source} --fields {field}",
        "frequency",
        "b",
    ),
    TuiAction(
        "filter",
        "Filter sample",
        'undatum select {source} --filter "{filter}"',
        "filter_sample",
        "b",
    ),
    TuiAction("export", "Export current view", "undatum convert {source} OUT", "export_view", "b"),
    TuiAction(
        "sql",
        "Run SQL",
        'undatum sql "SELECT * FROM data LIMIT {sql_limit}" {source}',
        "sql",
        "c",
    ),
    TuiAction(
        "convert",
        "Convert / save as (full file)",
        "undatum convert {source} OUT --low-memory",
        "convert_save",
        "d",
    ),
    TuiAction(
        "validate",
        "Validate sample",
        "undatum validate {source}",
        "validate_sample",
        "d",
    ),
    TuiAction(
        "mask",
        "Mask selected fields (preview)",
        "undatum mask {source} --fields {field} --method redact",
        "mask_preview",
        "d",
    ),
    TuiAction(
        "mask_write",
        "Mask and write file",
        "undatum mask {source} --output OUT --fields {field} --method redact",
        "mask_write",
        "d",
    ),
    TuiAction(
        "pipeline",
        "Export pipeline YAML",
        "undatum pipeline run pipeline.yml",
        "export_pipeline",
        "d",
    ),
)


def get_action(action_id: str) -> TuiAction | None:
    """Return the palette action with this id, if any."""
    for action in TUI_ACTIONS:
        if action.id == action_id:
            return action
    return None


def filter_actions(query: str, actions: tuple[TuiAction, ...] | None = None) -> list[TuiAction]:
    """Substring match on id, title, and CLI template."""
    items = list(actions if actions is not None else TUI_ACTIONS)
    needle = (query or "").strip().lower()
    if not needle:
        return items
    return [
        action
        for action in items
        if needle in action.id.lower()
        or needle in action.title.lower()
        or needle in action.cli_template.lower()
    ]


def render_cli(action: TuiAction, session: SessionState | None, field: str = "FIELD") -> str:
    """Fill a CLI template from the current session."""
    source = session.source if session else "FILE"
    filter_expr = (session.filter_expr if session else None) or "EXPR"
    return action.cli_template.format(
        source=source,
        field=field or "FIELD",
        filter=filter_expr,
        sql_limit=DEFAULT_SQL_LIMIT,
    )
