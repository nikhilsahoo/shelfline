from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from epub_tui.library import Bookmark, LibraryRepository, ReadingProgress
from epub_tui.reader import EpubPreview
from epub_tui.tui.widgets import StatusLine


class EpubReaderScreen(Screen[None]):
    KEY_HINT = "Keys: n next | p previous | m bookmark | b back | l library | c catalogs"
    BINDINGS = [
        ("n", "next_section", "Next"),
        ("p", "previous_section", "Previous"),
        ("m", "add_bookmark", "Bookmark"),
        ("b", "go_back", "Back"),
    ]

    def __init__(
        self,
        preview: EpubPreview,
        *,
        section_index: int = 0,
        library: LibraryRepository | None = None,
        book_path: Path | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.preview = preview
        self.library = library
        self.book_path = book_path
        self._progress_load_error: str | None = None
        self.section_index = self._initial_section_index(section_index)

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

    def on_mount(self) -> None:
        if self._progress_load_error is not None:
            self._set_status(f"Progress unavailable: {self._progress_load_error}")

    def action_next_section(self) -> None:
        next_index = self.preview.next_section_index(self.section_index)
        if next_index == self.section_index:
            return
        self.section_index = next_index
        self._refresh_section()
        self._save_progress()

    def action_previous_section(self) -> None:
        previous_index = self.preview.previous_section_index(self.section_index)
        if previous_index == self.section_index:
            return
        self.section_index = previous_index
        self._refresh_section()
        self._save_progress()

    def action_go_back(self) -> None:
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()
            return
        self.query_one("#status-line", StatusLine).set_message("No previous screen")

    def action_add_bookmark(self) -> None:
        if self.library is None or self.book_path is None:
            self._set_status("Bookmark requires library-backed book")
            return

        section = self.preview.section_at(self.section_index)
        position = 0
        try:
            deleted_count = self.library.delete_bookmarks_at_position(
                self.book_path,
                section_index=self.section_index,
                position=position,
            )
            if deleted_count > 0:
                self._set_status("Bookmark removed")
                return

            self.library.add_bookmark(
                Bookmark(
                    local_file_path=self.book_path,
                    section_index=self.section_index,
                    position=position,
                    label=section.heading,
                )
            )
        except Exception as error:
            self._set_status(f"Bookmark not saved: {error}")
            return

        self._set_status("Bookmark added")

    def _refresh_section(self) -> None:
        section = self.preview.section_at(self.section_index)
        self.query_one("#reader-heading", StatusLine).set_message(section.heading)
        self.query_one("#reader-body-text", Static).update(section.text)
        self.query_one("#reader-body", VerticalScroll).scroll_to(y=0, animate=False)
        self.query_one("#reader-progress", StatusLine).set_message(
            self.preview.progress_label(self.section_index)
        )

    def _initial_section_index(self, section_index: int) -> int:
        if self.library is None or self.book_path is None:
            return self._clamp_section_index(section_index)

        try:
            progress = self.library.get_reading_progress(self.book_path)
        except Exception as error:
            self._progress_load_error = str(error)
            return self._clamp_section_index(section_index)

        if progress is None:
            return self._clamp_section_index(section_index)
        return self._clamp_section_index(progress.section_index)

    def _clamp_section_index(self, section_index: int) -> int:
        if self.preview.section_count == 0:
            return 0
        return max(0, min(section_index, self.preview.section_count - 1))

    def _save_progress(self) -> None:
        if self.library is None or self.book_path is None:
            return
        try:
            self.library.save_reading_progress(
                ReadingProgress(
                    local_file_path=self.book_path,
                    section_index=self.section_index,
                    position=0,
                )
            )
        except Exception as error:
            self._set_status(f"Progress not saved: {error}")

    def _set_status(self, message: str) -> None:
        self.query_one("#status-line", StatusLine).set_message(message)
