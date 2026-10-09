"""Help overlay for the undatum TUI."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

HELP_TEXT = """\
undatum tui — explore a sample, not the whole file.

 q                 Quit
 ?                 This help
 o                 Open another file
 u                 Path or cloud URI (s3://, gs://, az://)
 s                 Profile (full file, via undatum stats)
 f                 Frequency on the selected grid column
 /                 Filter the loaded sample
 e                 Export the current view (sample)
 w                 Convert / save as (full file, --low-memory)
 v                 Validate the loaded sample
 m                 Mask selected fields (sample preview)
 p                 Export session as pipeline YAML
 :                 Command palette (shows equivalent CLI)
 ctrl+s            SQL against the source file (view: data)
 tab               Cycle fields / grid
 arrows / PgUp/Dn  Scroll the grid

The grid is a bounded sample. Frequency, filter, validate, and mask
preview apply to that sample. Profile, SQL, convert, and mask-write
scan or write the source file.

  undatum table FILE --limit 200
  undatum stats FILE
  undatum convert FILE OUT --low-memory
  undatum validate FILE --rules rules.yaml
  undatum mask FILE --fields email --method redact --output OUT
  undatum pipeline run pipeline.yml

Press any key to close this help.
"""


class HelpScreen(ModalScreen[None]):
    """Modal keybinding help."""

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close", show=False),
        Binding("q", "dismiss_help", "Close", show=False),
        Binding("question_mark", "dismiss_help", "Close", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static(HELP_TEXT, id="help-text")

    def on_key(self, event) -> None:
        event.stop()
        self.dismiss()

    def action_dismiss_help(self) -> None:
        self.dismiss()
