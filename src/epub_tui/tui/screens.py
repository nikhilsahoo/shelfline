from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from epub_tui.catalog.models import CatalogEntry, CatalogFeed
from epub_tui.config import AppConfig
from epub_tui.downloads import DownloadProgress
from epub_tui.library import BookRecord, LibraryRepository
from epub_tui.reader import EpubPreview
from epub_tui.tui.widgets import (
    BusyIndicator,
    CoverDisplay,
    DownloadProgressDisplay,
    StatusLine,
)


class SetupScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Setup", id="setup-title")
        yield StatusLine("Ready", id="status-line")
        yield Footer()

    def validate_library_path(self, path: str | Path) -> str | None:
        if isinstance(path, str) and not path.strip():
            return "Library path is required"

        library_path = Path(path).expanduser()
        if not library_path.exists():
            return "Library path must exist"
        if not library_path.is_dir():
            return "Library path must be a directory"
        return None


class CatalogsScreen(Screen[None]):
    def __init__(self, config: AppConfig, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine(self._catalog_text(), id="catalog-list")
        yield BusyIndicator(id="busy-indicator")
        yield StatusLine("Ready", id="status-line")
        yield Footer()

    def begin_outgoing_call(self, message: str) -> None:
        self.query_one("#busy-indicator", BusyIndicator).start(message)
        self.query_one("#status-line", StatusLine).set_message(message)

    def finish_outgoing_call(self, message: str = "Ready") -> None:
        self.query_one("#busy-indicator", BusyIndicator).stop()
        self.query_one("#status-line", StatusLine).set_message(message)

    def _catalog_text(self) -> str:
        if not self.config.catalogs:
            return "No catalogs configured"
        return "\n".join(catalog.name for catalog in self.config.catalogs)


class FeedScreen(Screen[None]):
    def __init__(self, feed: CatalogFeed, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.feed = feed

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine(self._feed_text(), id="feed-body")
        yield BusyIndicator(id="busy-indicator")
        yield StatusLine("Ready", id="status-line")
        yield Footer()

    def begin_fetch(self, message: str = "Fetching feed") -> None:
        self._begin_outgoing_call(message)

    def begin_refresh(self, message: str = "Refreshing feed") -> None:
        self._begin_outgoing_call(message)

    def begin_navigation(self, message: str = "Opening catalog link") -> None:
        self._begin_outgoing_call(message)

    def finish_outgoing_call(self, message: str = "Ready") -> None:
        self.query_one("#busy-indicator", BusyIndicator).stop()
        self.query_one("#status-line", StatusLine).set_message(message)

    def _begin_outgoing_call(self, message: str) -> None:
        self.query_one("#busy-indicator", BusyIndicator).start(message)
        self.query_one("#status-line", StatusLine).set_message(message)

    def _feed_text(self) -> str:
        lines = [self.feed.title, self.feed.source_url]
        if self.feed.updated:
            lines.append(f"Updated: {self.feed.updated}")
        if not self.feed.entries:
            lines.append("No entries")
            return "\n".join(lines)

        for index, entry in enumerate(self.feed.entries, start=1):
            authors = ", ".join(entry.authors) if entry.authors else "Unknown author"
            lines.append(f"{index}. {entry.title} - {authors}")
        return "\n".join(lines)


class EntryScreen(Screen[None]):
    def __init__(self, entry: CatalogEntry, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.entry = entry

    def compose(self) -> ComposeResult:
        yield Header()
        yield CoverDisplay(
            title=self.entry.title,
            authors=self.entry.authors,
            image_path=self.entry.cover_image_url or self.entry.thumbnail_url,
            id="cover-display",
        )
        yield StatusLine(self._entry_text(), id="entry-body")
        yield BusyIndicator(id="busy-indicator")
        yield StatusLine("Ready", id="status-line")
        yield Footer()

    def begin_download(self, message: str = "Starting download") -> None:
        self.query_one("#busy-indicator", BusyIndicator).start(message)
        self.query_one("#status-line", StatusLine).set_message(message)

    def finish_download(self, message: str = "Ready") -> None:
        self.query_one("#busy-indicator", BusyIndicator).stop()
        self.query_one("#status-line", StatusLine).set_message(message)

    def _entry_text(self) -> str:
        lines = [self.entry.title]
        if self.entry.summary:
            lines.append(self.entry.summary)
        if self.entry.updated:
            lines.append(f"Updated: {self.entry.updated}")
        if not self.entry.acquisition_links:
            lines.append("No acquisition links")
            return "\n".join(lines)

        lines.append("Acquisitions:")
        for link in self.entry.acquisition_links:
            label = link.title or link.media_type
            size = f" ({link.size} bytes)" if link.size is not None else ""
            lines.append(f"- {label}: {link.media_type} {link.href}{size}")
        return "\n".join(lines)


class DownloadStatusScreen(Screen[None]):
    def __init__(
        self,
        progress: DownloadProgress | None = None,
        *,
        status: str = "No download active",
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.progress = progress
        self.status = status

    def compose(self) -> ComposeResult:
        yield Header()
        yield DownloadProgressDisplay(self.progress, id="download-progress")
        yield StatusLine(self.status, id="download-status")
        yield Footer()

    def update_progress(self, progress: DownloadProgress, status: str | None = None) -> None:
        self.progress = progress
        self.query_one("#download-progress", DownloadProgressDisplay).update_progress(progress)
        if status is not None:
            self.status = status
            self.query_one("#download-status", StatusLine).set_message(status)


class LibraryScreen(Screen[None]):
    def __init__(
        self,
        *,
        library: LibraryRepository | None = None,
        books: list[BookRecord] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.library = library
        self.books = list(books) if books is not None else []
        self.selected_index = 0
        if self.library is not None:
            self.books = self.library.list_books()

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine(self._library_text(), id="library-body")
        yield StatusLine("Ready", id="status-line")
        yield Footer()

    def action_toggle_read(self) -> None:
        book = self.selected_book
        if book is None or self.library is None:
            self._set_status("No book selected")
            return

        self.library.mark_read(book.local_file_path, is_read=not book.is_read)
        self.refresh_books()
        self._set_status("Read status updated")

    def action_delete_book(self) -> None:
        book = self.selected_book
        if book is None or self.library is None:
            self._set_status("No book selected")
            return

        self.library.delete_book(book.local_file_path, remove_file=True)
        self.refresh_books()
        self._set_status("Book deleted")

    @property
    def selected_book(self) -> BookRecord | None:
        if not self.books:
            return None
        index = min(self.selected_index, len(self.books) - 1)
        return self.books[index]

    def refresh_books(self) -> None:
        if self.library is not None:
            self.books = self.library.list_books()
        if self.selected_index >= len(self.books):
            self.selected_index = max(0, len(self.books) - 1)
        self.query_one("#library-body", StatusLine).set_message(self._library_text())

    def _set_status(self, message: str) -> None:
        self.query_one("#status-line", StatusLine).set_message(message)

    def _library_text(self) -> str:
        if not self.books:
            return "No downloaded books"

        lines: list[str] = []
        for index, book in enumerate(self.books, start=1):
            authors = ", ".join(book.authors) if book.authors else "Unknown author"
            read_state = "Read" if book.is_read else "Unread"
            lines.append(f"{index}. {book.title} - {authors} [{read_state}]")
            lines.append(str(book.local_file_path))
        return "\n".join(lines)


class EpubPreviewScreen(Screen[None]):
    def __init__(self, preview: EpubPreview, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.preview = preview

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine(self._preview_text(), id="preview-body")
        yield Footer()

    def _preview_text(self) -> str:
        lines = [self.preview.title, "Outline:"]
        if not self.preview.outline:
            lines.append("No outline")
        for item in self.preview.outline:
            lines.append(f"- {item.title}")

        lines.append("Sections:")
        for section in self.preview.sections:
            lines.append(section.heading)
            lines.append(section.text)
        return "\n".join(lines)


class CatalogAuthScreen(Screen[None]):
    def __init__(self, catalog: object, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.catalog = catalog
        auth = getattr(catalog, "auth", None) or {}
        self.credentials = {
            "username": str(auth.get("username", "")),
            "password": str(auth.get("password", "")),
        }

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine(self._auth_text(), id="auth-body")
        yield Footer()

    def _auth_text(self) -> str:
        name = getattr(self.catalog, "name", "Catalog")
        username = self.credentials["username"] or "(none)"
        password_text = "(set)" if self.credentials["password"] else "(none)"
        return f"{name}\nUsername: {username}\nPassword: {password_text}"
