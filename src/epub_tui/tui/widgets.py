from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container
from textual.widgets import Static

from epub_tui.catalog.models import CatalogEntry
from epub_tui.downloads import DownloadProgress
from epub_tui.library import BookRecord


class BusyIndicator(Static):
    """Small status widget used while a screen waits on outgoing work."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        super().__init__(message, **kwargs)
        self._renderable = message

    @property
    def renderable(self) -> str:
        return self._renderable

    def start(self, message: str) -> None:
        self._renderable = message
        self.update(message)

    def stop(self) -> None:
        self._renderable = ""
        self.update("")


class StatusLine(Static):
    def __init__(self, message: str = "Ready", **kwargs: object) -> None:
        super().__init__(message, **kwargs)
        self._renderable = message

    @property
    def renderable(self) -> str:
        return self._renderable

    def set_message(self, message: str) -> None:
        self._renderable = message
        self.update(message)


class CatalogEntryRow(Container):
    def __init__(
        self,
        entry: CatalogEntry,
        *,
        index: int,
        selected: bool = False,
        **kwargs: object,
    ) -> None:
        self.entry = entry
        self.index = index
        self.selected = selected
        classes = f"feed-entry-row {self.kind_class}"
        if selected:
            classes = f"{classes} selected"
        super().__init__(id=f"feed-entry-{index}", classes=classes, **kwargs)

    @property
    def kind(self) -> str:
        if self.entry.navigation_url is not None:
            return "Folder"
        if self.entry.acquisition_links:
            return "Book"
        return "Entry"

    @property
    def kind_class(self) -> str:
        return f"kind-{self.kind.lower()}"

    @property
    def renderable(self) -> str:
        return self._row_text()

    def compose(self) -> ComposeResult:
        yield Static(">" if self.selected else " ", classes="row-marker")
        yield Static(f"{self.index + 1}.", classes="row-index")
        yield Static(self.kind, classes="row-kind")
        yield Static(self.entry.title, classes="row-title")
        yield Static(self._meta_text(), classes="row-meta")

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        if selected:
            self.add_class("selected")
        else:
            self.remove_class("selected")
        if self.is_mounted:
            self.query_one(".row-marker", Static).update(">" if selected else " ")

    def _meta_text(self) -> str:
        if self.entry.navigation_url is not None:
            return self.entry.updated or "Browse catalog"
        if self.entry.authors:
            return ", ".join(self.entry.authors)
        if self.entry.acquisition_links:
            return "Unknown author"
        return self.entry.updated or ""

    def _row_text(self) -> str:
        label = f"[{self.kind}] {self.entry.title}"
        meta = self._meta_text()
        if meta:
            label = f"{label} - {meta}"
        return f"{'>' if self.selected else ' '} {self.index + 1}. {label}"


class FeedEntryList(Container):
    def __init__(
        self,
        *,
        breadcrumbs: list[str],
        source_url: str,
        updated: str | None,
        entries: list[CatalogEntry],
        selected_index: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__(id="feed-body", classes="feed-entry-list", **kwargs)
        self.breadcrumbs = breadcrumbs
        self.source_url = source_url
        self.updated = updated
        self.entries = entries
        self.selected_index = selected_index

    @property
    def renderable(self) -> str:
        return self.render_text(
            self.breadcrumbs,
            self.source_url,
            self.updated,
            self.entries,
            self.selected_index,
        )

    def compose(self) -> ComposeResult:
        yield Static(" > ".join(self.breadcrumbs), id="feed-breadcrumbs", classes="feed-breadcrumbs")
        yield Static(self.source_url, id="feed-source", classes="feed-source")
        if self.updated:
            yield Static(f"Updated: {self.updated}", id="feed-updated", classes="feed-updated")
        if not self.entries:
            yield Static("No entries", classes="empty-state")
            return
        for index, entry in enumerate(self.entries):
            yield CatalogEntryRow(
                entry,
                index=index,
                selected=index == self.selected_index,
            )

    def set_selected_index(self, selected_index: int) -> None:
        self.selected_index = selected_index
        for row in self.query(CatalogEntryRow):
            row.set_selected(row.index == selected_index)

    @staticmethod
    def render_text(
        breadcrumbs: list[str],
        source_url: str,
        updated: str | None,
        entries: list[CatalogEntry],
        selected_index: int,
    ) -> str:
        lines = [" > ".join(breadcrumbs), source_url]
        if updated:
            lines.append(f"Updated: {updated}")
        if not entries:
            lines.append("No entries")
            return "\n".join(lines)
        for index, entry in enumerate(entries):
            lines.append(CatalogEntryRow(entry, index=index, selected=index == selected_index).renderable)
        return "\n".join(lines)


class LibraryBookRow(Container):
    def __init__(
        self,
        book: BookRecord,
        *,
        index: int,
        selected: bool = False,
        **kwargs: object,
    ) -> None:
        self.book = book
        self.index = index
        self.selected = selected
        state_class = "state-read" if book.is_read else "state-unread"
        classes = f"library-book-row {state_class}"
        if selected:
            classes = f"{classes} selected"
        super().__init__(id=f"library-book-{index}", classes=classes, **kwargs)

    @property
    def renderable(self) -> str:
        return self._row_text()

    def compose(self) -> ComposeResult:
        yield Static(">" if self.selected else " ", classes="row-marker")
        yield Static(f"{self.index + 1}.", classes="row-index")
        yield Static(self.book.title, classes="row-title")
        yield Static(self._authors_text(), classes="row-meta")
        yield Static(self._metadata_text(), classes="row-metadata")
        yield Static(str(self.book.local_file_path), classes="row-path")

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        if selected:
            self.add_class("selected")
        else:
            self.remove_class("selected")
        if self.is_mounted:
            self.query_one(".row-marker", Static).update(">" if selected else " ")

    def update_book(self, book: BookRecord, *, index: int, selected: bool) -> None:
        self.book = book
        self.index = index
        self.display = True
        self.remove_class("state-read")
        self.remove_class("state-unread")
        self.add_class("state-read" if book.is_read else "state-unread")
        self.set_selected(selected)
        if not self.is_mounted:
            return
        self.query_one(".row-index", Static).update(f"{index + 1}.")
        self.query_one(".row-title", Static).update(book.title)
        self.query_one(".row-meta", Static).update(self._authors_text())
        self.query_one(".row-metadata", Static).update(self._metadata_text())
        self.query_one(".row-path", Static).update(str(book.local_file_path))

    def _authors_text(self) -> str:
        return ", ".join(self.book.authors) if self.book.authors else "Unknown author"

    def _read_text(self) -> str:
        return "Read" if self.book.is_read else "Unread"

    def _progress_text(self) -> str:
        return "Finished" if self.book.is_read else "Not started"

    def _metadata_text(self) -> str:
        return (
            f"{self._read_text()} | {self._progress_text()} | "
            f"{self.book.media_type} | {self.book.source_catalog}"
        )

    def _row_text(self) -> str:
        return (
            f"{'>' if self.selected else ' '} {self.index + 1}. "
            f"{self.book.title} - {self._authors_text()} [{self._read_text()}] "
            f"{self.book.media_type} | {self.book.source_catalog}\n"
            f"  {self.book.local_file_path}"
        )


class LibraryBookList(Container):
    def __init__(
        self,
        books: list[BookRecord],
        *,
        selected_index: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__(id="library-body", classes="library-book-list", **kwargs)
        self.books = books
        self.selected_index = selected_index

    @property
    def renderable(self) -> str:
        return self.render_text(self.books, self.selected_index)

    def compose(self) -> ComposeResult:
        empty_state = Static("No downloaded books", id="library-empty", classes="empty-state")
        empty_state.display = not self.books
        yield empty_state
        yield from self._book_widgets()

    def set_books(self, books: list[BookRecord], selected_index: int) -> None:
        self.books = books
        self.selected_index = selected_index
        self.query_one("#library-empty", Static).display = not books
        rows = list(self.query(LibraryBookRow))
        for index, book in enumerate(books):
            selected = index == selected_index
            if index < len(rows):
                rows[index].update_book(book, index=index, selected=selected)
            else:
                self.mount(LibraryBookRow(book, index=index, selected=selected))
        for row in rows[len(books) :]:
            row.display = False
            row.set_selected(False)

    def set_selected_index(self, selected_index: int) -> None:
        self.selected_index = selected_index
        for row in self.query(LibraryBookRow):
            row.set_selected(row.index == selected_index)

    def _book_widgets(self) -> list[Static | LibraryBookRow]:
        return [
            LibraryBookRow(book, index=index, selected=index == self.selected_index)
            for index, book in enumerate(self.books)
        ]

    @staticmethod
    def render_text(books: list[BookRecord], selected_index: int) -> str:
        if not books:
            return "No downloaded books"
        return "\n".join(
            LibraryBookRow(book, index=index, selected=index == selected_index).renderable
            for index, book in enumerate(books)
        )


class DownloadProgressDisplay(Static):
    def __init__(self, progress: DownloadProgress | None = None, **kwargs: object) -> None:
        super().__init__("", **kwargs)
        self._renderable = ""
        if progress is None:
            self._set_text("No download active")
        else:
            self.update_progress(progress)

    @property
    def renderable(self) -> str:
        return self._renderable

    def update_progress(self, progress: DownloadProgress) -> None:
        if progress.total_bytes:
            percent = int(progress.percent or 0)
            self._set_text(f"{percent}% ({progress.bytes_received}/{progress.total_bytes} bytes)")
            return

        self._set_text(f"{progress.bytes_received} bytes received (indeterminate)")

    def _set_text(self, text: str) -> None:
        self._renderable = text
        self.update(text)


class CoverDisplay(Static):
    def __init__(
        self,
        *,
        title: str,
        authors: list[str] | tuple[str, ...] | None = None,
        image_path: str | Path | None = None,
        terminal_graphics: bool = False,
        **kwargs: object,
    ) -> None:
        self.title = title
        self.authors = list(authors or [])
        self.image_path = Path(image_path) if image_path is not None else None
        self.terminal_graphics = terminal_graphics
        renderable = self._render_cover()
        super().__init__(renderable, **kwargs)
        self._renderable = renderable

    @property
    def renderable(self) -> str:
        return self._renderable

    def _render_cover(self) -> str:
        author_text = ", ".join(self.authors) if self.authors else "Unknown author"
        return f"{self.title}\n{author_text}"
