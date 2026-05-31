from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from epub_tui.reader import EpubPreview
from epub_tui.tui.widgets import StatusLine


class EpubReaderScreen(Screen[None]):
    KEY_HINT = "Keys: n next | p previous | b back | l library | c catalogs"
    BINDINGS = [
        ("n", "next_section", "Next"),
        ("p", "previous_section", "Previous"),
        ("b", "go_back", "Back"),
    ]

    def __init__(
        self,
        preview: EpubPreview,
        *,
        section_index: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.preview = preview
        self.section_index = section_index

    def compose(self) -> ComposeResult:
        section = self.preview.section_at(self.section_index)
        yield Header()
        yield StatusLine(self.preview.title, id="reader-title")
        yield StatusLine(section.heading, id="reader-heading")
        with VerticalScroll(id="reader-body"):
            yield Static(section.text, id="reader-body-text")
        yield StatusLine(self.preview.progress_label(self.section_index), id="reader-progress")
        yield StatusLine(self.KEY_HINT, id="status-line")
        yield Footer()

    def action_next_section(self) -> None:
        self.section_index = self.preview.next_section_index(self.section_index)
        self._refresh_section()

    def action_previous_section(self) -> None:
        self.section_index = self.preview.previous_section_index(self.section_index)
        self._refresh_section()

    def action_go_back(self) -> None:
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
            return
        self.query_one("#status-line", StatusLine).set_message("No previous screen")

    def _refresh_section(self) -> None:
        section = self.preview.section_at(self.section_index)
        self.query_one("#reader-heading", StatusLine).set_message(section.heading)
        self.query_one("#reader-body-text", Static).update(section.text)
        self.query_one("#reader-progress", StatusLine).set_message(
            self.preview.progress_label(self.section_index)
        )
