from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import Header, Static

from shelfline.config import AppPreferences, ReaderPreferences
from shelfline.library import Bookmark, LibraryRepository, ReadingProgress
from shelfline.reader import EpubOutlineItem, EpubPreview
from shelfline.tui.layout import KeyHintFooter
from shelfline.tui.widgets import StatusLine


class ReaderChrome(Container):
    def __init__(
        self,
        title: str,
        progress: str,
        *,
        show_progress: bool = True,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.title = title
        self.progress = progress
        self.show_progress = show_progress

    @property
    def renderable(self) -> str:
        return f"{self.title}\n{self.progress}"

    def compose(self) -> ComposeResult:
        yield StatusLine(self.title, id="reader-title", classes="reader-title")
        progress = StatusLine(
            self.progress,
            id="reader-progress",
            classes="reader-progress",
        )
        progress.display = self.show_progress
        yield progress


class ReaderTocRow(Static):
    def __init__(
        self,
        entry: EpubOutlineItem,
        *,
        index: int,
        selected: bool = False,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.entry = entry
        self.index = index
        self.selected = selected

    def compose(self) -> ComposeResult:
        yield Static(self._row_text(), classes="toc-row-title")

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self.query_one(".toc-row-title", Static).update(self._row_text())

    def _row_text(self) -> str:
        prefix = ">" if self.selected else " "
        return f"{prefix} {self.entry.title}"


class ReaderTocList(VerticalScroll):
    def __init__(
        self,
        entries: tuple[EpubOutlineItem, ...],
        *,
        selected_index: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__(id="toc-list", classes="toc-list", **kwargs)
        self.entries = entries
        self.selected_index = selected_index

    def compose(self) -> ComposeResult:
        empty_state = Static(
            "No table of contents available",
            id="toc-empty",
            classes="empty-state",
        )
        empty_state.display = not self.entries
        yield empty_state
        yield from self._row_widgets()

    def render(self) -> str:
        if not self.entries:
            return "No table of contents available"
        return "\n".join(
            self._row_text(entry, index) for index, entry in enumerate(self.entries)
        )

    def set_selected_index(self, selected_index: int) -> None:
        self.selected_index = selected_index
        selected_row: ReaderTocRow | None = None
        for row in self.query(ReaderTocRow):
            selected = row.index == selected_index
            row.set_selected(selected)
            if selected:
                selected_row = row
        if selected_row is not None:
            self.scroll_to_widget(selected_row, animate=False, immediate=True)

    def _row_widgets(self) -> list[ReaderTocRow]:
        return [
            ReaderTocRow(
                entry,
                id=f"toc-row-{index}",
                index=index,
                selected=index == self.selected_index,
            )
            for index, entry in enumerate(self.entries)
        ]

    def _row_text(self, entry: EpubOutlineItem, index: int) -> str:
        prefix = ">" if index == self.selected_index else " "
        return f"{prefix} {entry.title}"


class ReaderTocScreen(Screen[None]):
    KEY_HINT = "Keys: j down | k up | enter jump | b back"
    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("enter", "jump_to_section", "Jump"),
        ("b", "dismiss_toc", "Back"),
    ]

    def __init__(self, reader: EpubReaderScreen, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.reader = reader
        self.entries = self._toc_entries(reader.preview)
        self.selected_index = self._initial_selected_index()

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="toc-surface"):
            yield StatusLine("Table of Contents", id="toc-title")
            yield ReaderTocList(self.entries, selected_index=self.selected_index)
        yield KeyHintFooter(self.KEY_HINT)

    def action_cursor_down(self) -> None:
        if not self.entries:
            return
        self.selected_index = min(self.selected_index + 1, len(self.entries) - 1)
        self._refresh_selection()

    def action_cursor_up(self) -> None:
        if not self.entries:
            return
        self.selected_index = max(self.selected_index - 1, 0)
        self._refresh_selection()

    def action_jump_to_section(self) -> None:
        if not self.entries:
            self.app.pop_screen()
            return
        self.reader.jump_to_section(self.entries[self.selected_index].section_index)
        self.app.pop_screen()

    def action_dismiss_toc(self) -> None:
        self.app.pop_screen()

    def _initial_selected_index(self) -> int:
        for index, entry in enumerate(self.entries):
            if entry.section_index == self.reader.section_index:
                return index
        return 0

    def _refresh_selection(self) -> None:
        self.query_one("#toc-list", ReaderTocList).set_selected_index(
            self.selected_index
        )

    def _toc_entries(self, preview: EpubPreview) -> tuple[EpubOutlineItem, ...]:
        if preview.outline:
            return preview.outline
        return tuple(
            EpubOutlineItem(title=section.heading, section_index=index)
            for index, section in enumerate(preview.sections)
        )


class ReaderPreferencesScreen(Screen[None]):
    KEY_HINT = "Keys: n narrow | m medium | w wide | b back"
    BINDINGS = [
        ("n", "set_narrow", "Narrow"),
        ("m", "set_medium", "Medium"),
        ("w", "set_wide", "Wide"),
        ("b", "dismiss_options", "Back"),
    ]

    def __init__(self, reader: EpubReaderScreen, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.reader = reader

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="reader-options"):
            yield StatusLine("Reader Options", id="reader-options-title")
            yield StatusLine("Width: n narrow | m medium | w wide", id="reader-options-width")
        yield KeyHintFooter(self.KEY_HINT)

    def action_set_narrow(self) -> None:
        self._set_width("narrow")

    def action_set_medium(self) -> None:
        self._set_width("medium")

    def action_set_wide(self) -> None:
        self._set_width("wide")

    def action_dismiss_options(self) -> None:
        self.app.pop_screen()

    def _set_width(self, width: str) -> None:
        self.reader.update_preferences(replace(self.reader.preferences, width=width))
        self.app.pop_screen()


class EpubReaderScreen(Screen[None]):
    KEY_HINT = "Keys: n next | p previous | t toc | o options | m bookmark | b back | l library | c catalogs"
    BINDINGS = [
        ("n", "next_section", "Next"),
        ("p", "previous_section", "Previous"),
        ("t", "table_of_contents", "TOC"),
        ("o", "reader_options", "Options"),
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
        preferences: ReaderPreferences | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.preview = preview
        self.library = library
        self.book_path = book_path
        self.preferences = preferences or ReaderPreferences()
        self._progress_load_error: str | None = None
        self.section_index = self._initial_section_index(section_index)

    def compose(self) -> ComposeResult:
        section = self.preview.section_at(self.section_index)
        yield Header()
        with Container(id="reader-surface", classes="reader-surface"):
            with Container(id="reader-page", classes=self._reader_page_classes()):
                yield ReaderChrome(
                    self.preview.title,
                    self.preview.progress_label(self.section_index),
                    show_progress=self.preferences.show_progress,
                    id="reader-chrome",
                    classes="reader-chrome",
                )
                heading = StatusLine(
                    section.heading,
                    id="reader-heading",
                    classes="reader-heading",
                )
                heading.display = self.preferences.show_chapter_title
                yield heading
                with VerticalScroll(id="reader-body", classes="reader-body"):
                    yield Static(section.text, id="reader-body-text", classes="reader-text")
        yield StatusLine("Ready", id="status-line")
        yield KeyHintFooter(self.KEY_HINT)

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

    def action_table_of_contents(self) -> None:
        self.app.push_screen(ReaderTocScreen(self))

    def action_reader_options(self) -> None:
        self.app.push_screen(ReaderPreferencesScreen(self))

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

    def jump_to_section(self, section_index: int) -> None:
        self.section_index = self._clamp_section_index(section_index)
        self._refresh_section()
        self._save_progress()

    def update_preferences(self, preferences: ReaderPreferences) -> None:
        self.preferences = preferences
        app_config = getattr(self.app, "config", None)
        app_preferences = getattr(app_config, "preferences", None)
        if isinstance(app_preferences, AppPreferences):
            self.app.config = replace(  # type: ignore[attr-defined]
                app_config,
                preferences=replace(app_preferences, reader=preferences),
            )

        save_app_config = getattr(self.app, "save_config", None)
        if callable(save_app_config):
            try:
                save_app_config()
            except Exception as error:
                self._set_status(f"Preferences not saved: {error}")

        self._apply_preference_classes()

    def _refresh_section(self) -> None:
        section = self.preview.section_at(self.section_index)
        progress = self.preview.progress_label(self.section_index)
        self.query_one("#reader-heading", StatusLine).set_message(section.heading)
        self.query_one("#reader-body-text", Static).update(section.text)
        self.query_one("#reader-body", VerticalScroll).scroll_to(y=0, animate=False)
        self.query_one("#reader-progress", StatusLine).set_message(progress)
        self.query_one("#reader-chrome", ReaderChrome).progress = progress

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

    def _reader_page_classes(self) -> str:
        return " ".join(
            (
                "reader-page",
                f"reader-width-{self.preferences.width}",
                f"reader-theme-{self.preferences.theme}",
                f"reader-spacing-{self.preferences.paragraph_spacing}",
            )
        )

    def _apply_preference_classes(self) -> None:
        page = self.query_one("#reader-page")
        for class_name in (
            "reader-width-narrow",
            "reader-width-medium",
            "reader-width-wide",
            "reader-theme-default",
            "reader-theme-warm",
            "reader-theme-high_contrast",
            "reader-spacing-compact",
            "reader-spacing-normal",
            "reader-spacing-relaxed",
        ):
            page.remove_class(class_name)
        page.add_class(f"reader-width-{self.preferences.width}")
        page.add_class(f"reader-theme-{self.preferences.theme}")
        page.add_class(f"reader-spacing-{self.preferences.paragraph_spacing}")
        self.query_one("#reader-progress", StatusLine).display = (
            self.preferences.show_progress
        )
        self.query_one("#reader-heading", StatusLine).display = (
            self.preferences.show_chapter_title
        )
        self.query_one("#reader-chrome", ReaderChrome).show_progress = (
            self.preferences.show_progress
        )

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
