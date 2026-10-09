"""Sample grid and field list for an open dataset."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from ...common.errors import UndatumError, ValidationError
from ..services import TuiServices
from ..session import SessionState


class PreviewScreen(Screen):
    """Bounded sample preview. Cells are not editable."""

    BINDINGS = [
        Binding("q", "app.quit", "Quit"),
        Binding("question_mark", "help", "Help"),
        Binding("o", "open_file", "Open"),
        Binding("s", "profile", "Profile"),
        Binding("f", "frequency", "Freq"),
        Binding("slash", "filter_sample", "Filter"),
        Binding("e", "export_view", "Export"),
        Binding("colon", "palette", "Palette"),
        Binding("ctrl+s", "sql", "SQL"),
        Binding("v", "validate_sample", "Validate"),
        Binding("m", "mask_preview", "Mask"),
        Binding("w", "convert_save", "Save as"),
        Binding("p", "export_pipeline", "Pipeline"),
    ]

    def __init__(self, session: SessionState) -> None:
        super().__init__()
        self.session = session

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="body"):
            with Vertical(id="fields-pane"):
                yield Static("Fields", id="fields-title")
                yield Static(id="fields")
            yield DataTable(id="grid", cursor_type="cell")
        yield Static(id="status")
        yield Static(id="cli")
        yield Footer()

    def on_mount(self) -> None:
        self._fill()

    def _fill(self) -> None:
        session = self.session
        field_lines = []
        for name in session.headers:
            kind = session.field_types.get(name, "")
            field_lines.append(f"{name}  {kind}".rstrip())
        self.query_one("#fields", Static).update(
            "\n".join(field_lines) if field_lines else "(no fields)"
        )

        table = self.query_one("#grid", DataTable)
        table.clear(columns=True)
        table.cursor_type = "cell"
        if session.headers:
            table.add_columns(*session.headers)
            for row in TuiServices().grid_rows(session):
                table.add_row(*row)

        visible = len(session.visible_rows())
        sample_note = f"sample {visible}/{len(session.sample_rows)}"
        if session.filter_expr:
            sample_note += f"  filter: {session.filter_expr}"
        if session.truncated:
            sample_note += f"  first {session.sample_limit} (not full file)"
        else:
            sample_note += "  (full file fits in sample)"
        encoding = session.encoding or "auto"
        fmt = session.format_name or "unknown"
        self.query_one("#status", Static).update(
            f"{session.source}  {fmt}  {encoding}  {sample_note}"
        )
        self.query_one("#cli", Static).update(f"$ {session.last_cli or ''}")
        self.sub_title = session.source

    def _selected_field(self) -> str:
        if not self.session.headers:
            raise ValidationError("No fields in the current sample", field="fields")
        table = self.query_one("#grid", DataTable)
        try:
            column = table.cursor_coordinate.column
        except Exception:
            column = 0
        if column < 0 or column >= len(self.session.headers):
            column = 0
        return self.session.headers[column]

    def _show_result(self, title: str, headers: list[str], rows: list[list[str]], cli: str) -> None:
        from .result import ResultScreen

        self.query_one("#cli", Static).update(f"$ {self.session.last_cli or cli}")
        self.app.push_screen(ResultScreen(title, headers, rows, cli))

    def _on_service_error(self, exc: BaseException) -> None:
        self.notify(str(exc), severity="error")

    def action_help(self) -> None:
        from .help import HelpScreen

        self.app.push_screen(HelpScreen())

    def action_open_file(self) -> None:
        from .browse import BrowseScreen

        history = getattr(self.app, "history_file", None)
        self.app.push_screen(BrowseScreen(history_file=history))

    def action_profile(self) -> None:
        self.notify("Running undatum stats…")
        self.run_worker(self._profile_in_thread, exclusive=True, thread=True, group="explore")

    def _profile_in_thread(self) -> None:
        try:
            headers, rows, cli = TuiServices().profile(self.session)
        except Exception as exc:
            self.app.call_from_thread(self._on_service_error, exc)
            return
        self.app.call_from_thread(self._show_result, "Profile", headers, rows, cli)

    def action_frequency(self) -> None:
        try:
            field = self._selected_field()
            headers, rows, cli = TuiServices().frequency(self.session, field)
        except UndatumError as exc:
            self.notify(str(exc), severity="error")
            return
        self._show_result(f"Frequency · {field}", headers, rows, cli)

    def action_filter_sample(self) -> None:
        from .prompt import PromptScreen

        def _apply(value: str | None) -> None:
            if value is None:
                return
            try:
                TuiServices().apply_filter(self.session, value)
            except UndatumError as exc:
                self.notify(str(exc), severity="error")
                return
            self._fill()

        self.app.push_screen(
            PromptScreen(
                "Filter sample (empty clears)",
                placeholder='name == "Alice"',
                value=self.session.filter_expr or "",
            ),
            _apply,
        )

    def action_export_view(self) -> None:
        from .prompt import PromptScreen

        def _export(value: str | None) -> None:
            if value is None:
                return
            try:
                cli = TuiServices().export_view(self.session, value.strip())
            except Exception as exc:
                self.notify(str(exc), severity="error")
                return
            self.query_one("#cli", Static).update(f"$ {cli}")
            self.notify(f"Wrote {value.strip()}")

        self.app.push_screen(
            PromptScreen("Export current view", placeholder="extract.jsonl"),
            _export,
        )

    def action_sql(self) -> None:
        from .sql import DEFAULT_SQL, SqlScreen

        def _run(value: str | None) -> None:
            if value is None:
                return
            self._pending_sql = value
            self.notify("Running undatum sql…")
            self.run_worker(self._sql_in_thread, exclusive=True, thread=True, group="explore")

        self.app.push_screen(SqlScreen(DEFAULT_SQL), _run)

    def _sql_in_thread(self) -> None:
        query = getattr(self, "_pending_sql", "")
        try:
            headers, rows, cli = TuiServices().run_sql(self.session, query)
        except Exception as exc:
            self.app.call_from_thread(self._on_service_error, exc)
            return
        self.app.call_from_thread(self._show_result, "SQL", headers, rows, cli)

    def action_palette(self) -> None:
        from ..actions import get_action, render_cli
        from .palette import PaletteScreen

        field = "FIELD"
        try:
            field = self._selected_field()
        except ValidationError:
            pass

        def _run(action_id: str | None) -> None:
            if not action_id:
                return
            action = get_action(action_id)
            if action is None:
                return
            self.session.last_cli = render_cli(action, self.session, field)
            self.query_one("#cli", Static).update(f"$ {self.session.last_cli}")
            handler = getattr(self, f"action_{action.handler}", None)
            if handler is None:
                return
            handler()

        self.app.push_screen(PaletteScreen(self.session, field), _run)

    def action_validate_sample(self) -> None:
        from .prompt import PromptScreen

        def _run(value: str | None) -> None:
            if value is None:
                return
            try:
                headers, rows, cli = TuiServices().validate_sample(self.session, value)
            except UndatumError as exc:
                self.notify(str(exc), severity="error")
                return
            self._show_result("Validate sample", headers, rows, cli)

        self.app.push_screen(
            PromptScreen(
                "Rules file (empty = sample completeness)",
                placeholder="rules.yaml",
            ),
            _run,
        )

    def action_mask_preview(self) -> None:
        from .prompt import PromptScreen

        default = ""
        try:
            default = self._selected_field()
        except ValidationError:
            pass

        def _run(value: str | None) -> None:
            if value is None:
                return
            try:
                headers, rows, cli = TuiServices().mask_preview(self.session, value)
            except UndatumError as exc:
                self.notify(str(exc), severity="error")
                return
            self._show_result("Mask preview (sample)", headers, rows, cli)

        self.app.push_screen(
            PromptScreen(
                "Fields to mask (comma-separated)", placeholder="email,phone", value=default
            ),
            _run,
        )

    def action_mask_write(self) -> None:
        from .prompt import PromptScreen

        default = ""
        try:
            default = self._selected_field()
        except ValidationError:
            pass

        def _after_fields(fields: str | None) -> None:
            if fields is None:
                return

            def _after_path(path: str | None) -> None:
                if path is None:
                    return
                self._pending_mask = (fields.strip(), path.strip())
                self.notify("Running undatum mask…")
                self.run_worker(
                    self._mask_write_in_thread, exclusive=True, thread=True, group="explore"
                )

            self.app.push_screen(
                PromptScreen("Write masked file", placeholder="masked.jsonl"),
                _after_path,
            )

        self.app.push_screen(
            PromptScreen(
                "Fields to mask (comma-separated)", placeholder="email,phone", value=default
            ),
            _after_fields,
        )

    def _mask_write_in_thread(self) -> None:
        fields, path = getattr(self, "_pending_mask", ("", ""))
        try:
            cli = TuiServices().mask_write(self.session, path, fields)
        except Exception as exc:
            self.app.call_from_thread(self._on_service_error, exc)
            return
        self.app.call_from_thread(self._on_wrote, cli, path)

    def action_convert_save(self) -> None:
        from .prompt import PromptScreen

        def _run(value: str | None) -> None:
            if value is None:
                return
            self._pending_convert = value.strip()
            self.notify("Running undatum convert --low-memory…")
            self.run_worker(self._convert_in_thread, exclusive=True, thread=True, group="explore")

        self.app.push_screen(
            PromptScreen("Convert / save as (full file)", placeholder="out.parquet"),
            _run,
        )

    def _convert_in_thread(self) -> None:
        path = getattr(self, "_pending_convert", "")
        try:
            cli = TuiServices().convert_save(self.session, path)
        except Exception as exc:
            self.app.call_from_thread(self._on_service_error, exc)
            return
        self.app.call_from_thread(self._on_wrote, cli, path)

    def action_export_pipeline(self) -> None:
        from .prompt import PromptScreen

        def _run(value: str | None) -> None:
            if value is None:
                return
            try:
                cli = TuiServices().export_pipeline(self.session, value.strip())
            except UndatumError as exc:
                self.notify(str(exc), severity="error")
                return
            self.query_one("#cli", Static).update(f"$ {cli}")
            self.notify(f"Wrote {value.strip()}")

        self.app.push_screen(
            PromptScreen("Pipeline YAML path", placeholder="pipeline.yml", value="pipeline.yml"),
            _run,
        )

    def _on_wrote(self, cli: str, path: str) -> None:
        self.query_one("#cli", Static).update(f"$ {cli}")
        self.notify(f"Wrote {path}")
