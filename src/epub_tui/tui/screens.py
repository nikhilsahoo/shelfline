from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Static

from epub_tui.catalog.models import CatalogEntry, CatalogFeed
from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.downloads import DownloadProgress
from epub_tui.library import BookRecord, LibraryRepository
from epub_tui.reader import EpubPreview, extract_epub_preview
from epub_tui.services import CatalogWorkflow
from epub_tui.tui.widgets import (
    BusyIndicator,
    CoverDisplay,
    DownloadProgressDisplay,
    StatusLine,
)


class SetupScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine("Library path", id="setup-title")
        yield Input(placeholder="Library path", id="library-path")
        yield Button("Save", id="save-library")
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

    async def complete_setup(self) -> None:
        path_input = self.query_one("#library-path", Input)
        library_path = Path(path_input.value).expanduser()
        error = self.validate_library_path(path_input.value)
        if error is not None:
            self.query_one("#status-line", StatusLine).set_message(error)
            return
        await self.app.complete_setup(library_path)  # type: ignore[attr-defined]

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-library":
            await self.complete_setup()


class CatalogsScreen(Screen[None]):
    KEY_HINT = "Keys: enter open | j/k select | a add catalog | l library"
    BINDINGS = [
        Binding("enter", "open_selected", "Open", priority=True),
        Binding("j", "cursor_down", "Down", priority=True),
        Binding("down", "cursor_down", "Down", priority=True),
        Binding("k", "cursor_up", "Up", priority=True),
        Binding("up", "cursor_up", "Up", priority=True),
    ]

    def __init__(
        self,
        config: AppConfig,
        *,
        workflow: CatalogWorkflow | None = None,
        show_add_form: bool = False,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.config = config
        self.workflow = workflow
        self.show_add_form = show_add_form
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine(self._catalog_text(), id="catalog-list")
        yield Button("New catalog", id="show-add-catalog")
        with Container(id="catalog-form"):
            yield Input(placeholder="Catalog name", id="catalog-name")
            yield Input(placeholder="OPDS URL", id="catalog-url")
            yield Input(placeholder="Basic Auth username", id="catalog-username")
            yield Input(placeholder="Basic Auth password", password=True, id="catalog-password")
            yield Button("Add catalog", id="add-catalog")
        yield BusyIndicator(id="busy-indicator")
        yield StatusLine(self.KEY_HINT, id="status-line")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#catalog-form", Container).display = self.show_add_form
        self.app.set_focus(None)
        self.call_after_refresh(lambda: self.app.set_focus(None))

    def begin_outgoing_call(self, message: str) -> None:
        self.query_one("#busy-indicator", BusyIndicator).start(message)
        self.query_one("#status-line", StatusLine).set_message(message)

    def finish_outgoing_call(self, message: str = "Ready") -> None:
        self.query_one("#busy-indicator", BusyIndicator).stop()
        self.query_one("#status-line", StatusLine).set_message(message)

    async def open_catalog(self, index: int = 0) -> None:
        if self.workflow is None:
            self.finish_outgoing_call("Catalog workflow is not available")
            return
        if index < 0 or index >= len(self.config.catalogs):
            self.finish_outgoing_call("Catalog is not available")
            return

        self.selected_index = index
        catalog = self.config.catalogs[index]
        feed = await self.workflow.fetch_catalog(
            catalog,
            on_status=lambda message: self.begin_outgoing_call(message),
        )
        self.finish_outgoing_call("Catalog loaded")
        await self.app.push_screen(FeedScreen(feed, catalog=catalog, workflow=self.workflow))

    async def action_open_selected(self) -> None:
        await self.open_catalog(self.selected_index)

    def action_cursor_down(self) -> None:
        self._move_selection(1)

    def action_cursor_up(self) -> None:
        self._move_selection(-1)

    def _move_selection(self, delta: int) -> None:
        if not self.config.catalogs:
            return
        self.selected_index = max(0, min(len(self.config.catalogs) - 1, self.selected_index + delta))
        self.query_one("#catalog-list", StatusLine).set_message(self._catalog_text())
        self.query_one("#status-line", StatusLine).set_message(
            f"Selected {self.config.catalogs[self.selected_index].name}"
        )

    def add_catalog_from_inputs(self) -> None:
        name = self.query_one("#catalog-name", Input).value.strip()
        url = self.query_one("#catalog-url", Input).value.strip()
        username = self.query_one("#catalog-username", Input).value
        password = self.query_one("#catalog-password", Input).value
        error = self._validate_catalog_input(name, url)
        if error is not None:
            self.query_one("#status-line", StatusLine).set_message(error)
            return

        auth = None
        if username or password:
            if not username or not password:
                self.query_one("#status-line", StatusLine).set_message(
                    "Basic Auth requires both username and password"
                )
                return
            auth = {"username": username, "password": password}

        catalog = CatalogConfig(name=name, url=url, auth=auth)
        self.app.add_catalog(catalog)  # type: ignore[attr-defined]
        if getattr(self.app, "config", None) is not None:
            self.config = self.app.config  # type: ignore[assignment]
        self.query_one("#catalog-list", StatusLine).set_message(self._catalog_text())
        self.query_one("#status-line", StatusLine).set_message("Catalog added")
        self.query_one("#catalog-name", Input).value = ""
        self.query_one("#catalog-url", Input).value = ""
        self.query_one("#catalog-username", Input).value = ""
        self.query_one("#catalog-password", Input).value = ""
        self.query_one("#catalog-form", Container).display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "show-add-catalog":
            self.action_toggle_add_catalog()
            return
        if event.button.id == "add-catalog":
            self.add_catalog_from_inputs()

    def action_toggle_add_catalog(self) -> None:
        form = self.query_one("#catalog-form", Container)
        form.display = not form.display
        self.query_one("#status-line", StatusLine).set_message(
            "Add catalog form shown" if form.display else "Add catalog form hidden"
        )

    def _validate_catalog_input(self, name: str, url: str) -> str | None:
        if not name:
            return "Catalog name is required"
        if any(catalog.name == name for catalog in self.config.catalogs):
            return f"Duplicate catalog name: {name}"
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "Catalog URL must be http or https"
        return None

    def _catalog_text(self) -> str:
        if not self.config.catalogs:
            return "No catalogs configured"
        return "\n".join(
            f"{'>' if index == self.selected_index else ' '} {catalog.name}"
            for index, catalog in enumerate(self.config.catalogs)
        )


class FeedScreen(Screen[None]):
    KEY_HINT = "Keys: enter open | j/k select | b back | c catalogs | l library"
    BINDINGS = [
        ("enter", "open_selected", "Open"),
        ("b", "go_back", "Back"),
        ("j", "cursor_down", "Down"),
        ("down", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("up", "cursor_up", "Up"),
    ]

    def __init__(
        self,
        feed: CatalogFeed,
        *,
        catalog: CatalogConfig | None = None,
        workflow: CatalogWorkflow | None = None,
        breadcrumbs: list[str] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.feed = feed
        self.catalog = catalog
        self.workflow = workflow
        self.breadcrumbs = list(breadcrumbs) if breadcrumbs is not None else ["Catalog", feed.title]
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine(self._feed_text(), id="feed-body")
        yield BusyIndicator(id="busy-indicator")
        yield StatusLine(self.KEY_HINT, id="status-line")
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

    async def open_entry(self, index: int = 0) -> None:
        if index < 0 or index >= len(self.feed.entries):
            self.finish_outgoing_call("Entry is not available")
            return
        self.selected_index = index
        entry = self.feed.entries[index]
        if entry.navigation_url is not None:
            if self.workflow is None or self.catalog is None:
                self.finish_outgoing_call("Catalog workflow is not available")
                return
            feed = await self.workflow.fetch_catalog(
                self.catalog,
                url=entry.navigation_url,
                on_status=lambda message: self._begin_outgoing_call(message),
            )
            self.finish_outgoing_call("Catalog loaded")
            await self.app.push_screen(
                FeedScreen(
                    feed,
                    catalog=self.catalog,
                    workflow=self.workflow,
                    breadcrumbs=[*self.breadcrumbs, feed.title],
                )
            )
            return

        await self.app.push_screen(EntryScreen(entry, catalog=self.catalog, workflow=self.workflow))

    async def action_open_selected(self) -> None:
        await self.open_entry(self.selected_index)

    def action_go_back(self) -> None:
        if len(self.app.screen_stack) <= 1:
            self.finish_outgoing_call("No parent feed")
            return
        self.app.pop_screen()

    def action_cursor_down(self) -> None:
        self._move_selection(1)

    def action_cursor_up(self) -> None:
        self._move_selection(-1)

    def _move_selection(self, delta: int) -> None:
        if not self.feed.entries:
            return
        self.selected_index = max(0, min(len(self.feed.entries) - 1, self.selected_index + delta))
        self.query_one("#feed-body", StatusLine).set_message(self._feed_text())
        self.query_one("#status-line", StatusLine).set_message(
            f"Selected {self.feed.entries[self.selected_index].title}"
        )

    def _begin_outgoing_call(self, message: str) -> None:
        self.query_one("#busy-indicator", BusyIndicator).start(message)
        self.query_one("#status-line", StatusLine).set_message(message)

    def _feed_text(self) -> str:
        lines = [" > ".join(self.breadcrumbs), self.feed.source_url]
        if self.feed.updated:
            lines.append(f"Updated: {self.feed.updated}")
        if not self.feed.entries:
            lines.append("No entries")
            return "\n".join(lines)

        for index, entry in enumerate(self.feed.entries, start=1):
            authors = ", ".join(entry.authors) if entry.authors else "Unknown author"
            marker = ">" if index - 1 == self.selected_index else " "
            lines.append(f"{marker} {index}. {self._entry_kind(entry)} {entry.title} - {authors}")
        return "\n".join(lines)

    def _entry_kind(self, entry: CatalogEntry) -> str:
        if entry.navigation_url is not None:
            return "[Folder]"
        if entry.acquisition_links:
            return "[Book]"
        return "[Entry]"


class EntryScreen(Screen[None]):
    KEY_HINT = "Keys: d download | j/k select | c catalogs | l library"
    BINDINGS = [
        ("d", "download_selected", "Download"),
        ("j", "cursor_down", "Down"),
        ("down", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("up", "cursor_up", "Up"),
    ]

    def __init__(
        self,
        entry: CatalogEntry,
        *,
        catalog: CatalogConfig | None = None,
        workflow: CatalogWorkflow | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.entry = entry
        self.catalog = catalog
        self.workflow = workflow
        self.selected_index = 0

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
        yield StatusLine(self.KEY_HINT, id="status-line")
        yield Footer()

    def begin_download(self, message: str = "Starting download") -> None:
        self.query_one("#busy-indicator", BusyIndicator).start(message)
        self.query_one("#status-line", StatusLine).set_message(message)

    def finish_download(self, message: str = "Ready") -> None:
        self.query_one("#busy-indicator", BusyIndicator).stop()
        self.query_one("#status-line", StatusLine).set_message(message)

    async def download_acquisition(self, index: int = 0) -> None:
        if self.workflow is None or self.catalog is None:
            self.finish_download("Download workflow is not available")
            return
        if index < 0 or index >= len(self.entry.acquisition_links):
            self.finish_download("Acquisition is not available")
            return

        status_screen = DownloadStatusScreen(status="Starting download...")
        await self.app.push_screen(status_screen)
        self.selected_index = index
        await self.workflow.download_acquisition(
            self.catalog,
            self.entry,
            link=self.entry.acquisition_links[index],
            on_status=status_screen.set_status,
            on_progress=lambda progress: status_screen.update_progress(progress),
        )
        status_screen.set_status("Download complete")

    async def action_download_selected(self) -> None:
        await self.download_acquisition(self.selected_index)

    def action_cursor_down(self) -> None:
        self._move_selection(1)

    def action_cursor_up(self) -> None:
        self._move_selection(-1)

    def _move_selection(self, delta: int) -> None:
        if not self.entry.acquisition_links:
            return
        self.selected_index = max(0, min(len(self.entry.acquisition_links) - 1, self.selected_index + delta))
        self.query_one("#entry-body", StatusLine).set_message(self._entry_text())
        link = self.entry.acquisition_links[self.selected_index]
        label = link.title or link.media_type
        self.query_one("#status-line", StatusLine).set_message(f"Selected {label}")

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
        for index, link in enumerate(self.entry.acquisition_links):
            label = link.title or link.media_type
            size = f" ({link.size} bytes)" if link.size is not None else ""
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} {label}: {link.media_type} {link.href}{size}")
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
        if self.is_mounted:
            self.query_one("#download-progress", DownloadProgressDisplay).update_progress(progress)
        if status is not None:
            self.set_status(status)

    def set_status(self, status: str) -> None:
        self.status = status
        if self.is_mounted:
            self.query_one("#download-status", StatusLine).set_message(status)


class LibraryScreen(Screen[None]):
    KEY_HINT = "Keys: enter preview | j/k select | r refresh | m read | x delete | c catalogs"
    BINDINGS = [
        ("enter", "open_selected", "Open"),
        ("j", "cursor_down", "Down"),
        ("down", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("up", "cursor_up", "Up"),
        ("r", "refresh_library", "Refresh"),
    ]

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
        yield StatusLine(self.KEY_HINT, id="status-line")
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

    def open_preview(self) -> None:
        book = self.selected_book
        if book is None:
            self._set_status("No book selected")
            return
        if book.media_type != "application/epub+zip":
            self._set_status("Preview is not implemented for this format")
            return
        self.app.push_screen(EpubPreviewScreen(extract_epub_preview(book.local_file_path)))

    def action_open_selected(self) -> None:
        self.open_preview()

    def action_cursor_down(self) -> None:
        self._move_selection(1)

    def action_cursor_up(self) -> None:
        self._move_selection(-1)

    def action_refresh_library(self) -> None:
        self.refresh_books()
        self._set_status("Library refreshed")

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

    def _move_selection(self, delta: int) -> None:
        if not self.books:
            return
        self.selected_index = max(0, min(len(self.books) - 1, self.selected_index + delta))
        self.query_one("#library-body", StatusLine).set_message(self._library_text())
        self._set_status(f"Selected {self.books[self.selected_index].title}")

    def _library_text(self) -> str:
        if not self.books:
            return "No downloaded books"

        lines: list[str] = []
        for index, book in enumerate(self.books, start=1):
            authors = ", ".join(book.authors) if book.authors else "Unknown author"
            read_state = "Read" if book.is_read else "Unread"
            marker = ">" if index - 1 == self.selected_index else " "
            lines.append(f"{marker} {index}. {book.title} - {authors} [{read_state}]")
            lines.append(f"  {book.local_file_path}")
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
