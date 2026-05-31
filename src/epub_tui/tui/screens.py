from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, Header, Input, Static

from epub_tui.catalog.models import CatalogEntry, CatalogFeed
from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.downloads import DownloadProgress
from epub_tui.library import BookRecord, LibraryRepository, LibrarySearch
from epub_tui.reader import EpubPreview, ReaderError, extract_epub_preview
from epub_tui.services import CatalogWorkflow
from epub_tui.tui.layout import AppShell, KeyHintFooter, replace_region
from epub_tui.tui.reader import EpubReaderScreen
from epub_tui.tui.widgets import (
    BusyIndicator,
    CoverDisplay,
    CatalogList,
    EntryDetailView,
    FeedEntryList,
    LibraryBookList,
    DownloadProgressDisplay,
    StatusLine,
)


class CatalogForm(Container):
    def __init__(self) -> None:
        super().__init__(id="catalog-form")

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Catalog name", id="catalog-name")
        yield Input(placeholder="OPDS URL", id="catalog-url")
        yield Input(placeholder="Basic Auth username", id="catalog-username")
        yield Input(placeholder="Basic Auth password", password=True, id="catalog-password")
        yield Button("Add catalog", id="add-catalog")
        yield Button("Cancel", id="cancel-add-catalog")


def _catalog_form() -> CatalogForm:
    return CatalogForm()


class CatalogActions(Container):
    def __init__(self) -> None:
        super().__init__(id="catalog-actions")

    def compose(self) -> ComposeResult:
        yield Button("New catalog", id="show-add-catalog")


class SetupScreen(Screen[None]):
    KEY_HINT = "Keys: tab focus | enter save | q quit"

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine("Library path", id="setup-title")
        yield Input(placeholder="Library path", id="library-path")
        yield Button("Save", id="save-library")
        yield StatusLine("Ready", id="status-line")
        yield KeyHintFooter(self.KEY_HINT)

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
        Binding("a", "toggle_add_catalog", "Add Catalog", priority=True),
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
        yield AppShell(area="Catalogs", key_hints=self.KEY_HINT)

    def on_mount(self) -> None:
        replace_region(
            self.query_one("#main-region"),
            CatalogList(self.config.catalogs, selected_index=self.selected_index),
            BusyIndicator(id="busy-indicator"),
            _catalog_form(),
            CatalogActions(),
        )
        replace_region(
            self.query_one("#detail-region"),
            StatusLine(self._selected_catalog_detail(), id="status-line"),
        )
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
        try:
            feed = await self.workflow.fetch_catalog(
                catalog,
                on_status=lambda message: self.begin_outgoing_call(message),
            )
        except Exception as exc:
            self.finish_outgoing_call(f"Catalog failed: {_error_message(exc)}")
            return
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
        self.query_one("#catalog-list", CatalogList).set_selected_index(self.selected_index)
        self.query_one("#status-line", StatusLine).set_message(self._selected_catalog_detail())

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
        self.selected_index = len(self.config.catalogs) - 1
        self.query_one("#catalog-list", CatalogList).set_catalogs(
            self.config.catalogs,
            self.selected_index,
        )
        self.query_one("#status-line", StatusLine).set_message(
            self._selected_catalog_detail("Catalog added")
        )
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
            return
        if event.button.id == "cancel-add-catalog":
            self.dismiss_add_catalog_form()

    def dismiss_add_catalog_form(self) -> None:
        self.query_one("#catalog-form", Container).display = False
        self.query_one("#status-line", StatusLine).set_message(
            self._selected_catalog_detail("Add catalog form hidden")
        )

    def action_toggle_add_catalog(self) -> None:
        form = self.query_one("#catalog-form", Container)
        form.display = not form.display
        self.query_one("#status-line", StatusLine).set_message(
            self._selected_catalog_detail(
                "Add catalog form shown" if form.display else "Add catalog form hidden"
            )
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
        return CatalogList.render_text(self.config.catalogs, self.selected_index)

    def _selected_catalog_detail(self, hint: str = "Press Enter to open") -> str:
        if not self.config.catalogs:
            empty_hint = hint if hint != "Press Enter to open" else "Press a to add a catalog"
            return f"No catalog selected\n{empty_hint}"
        catalog = self.config.catalogs[self.selected_index]
        auth_status = "Basic auth configured" if catalog.auth else "No auth configured"
        return (
            f"{catalog.name}\n"
            f"{catalog.url}\n"
            f"{auth_status}\n"
            f"{hint}"
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
        yield FeedEntryList(
            breadcrumbs=self.breadcrumbs,
            source_url=self.feed.source_url,
            updated=self.feed.updated,
            entries=self.feed.entries,
            selected_index=self.selected_index,
        )
        yield BusyIndicator(id="busy-indicator")
        yield StatusLine("Ready", id="status-line")
        yield KeyHintFooter(self.KEY_HINT)

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
            try:
                feed = await self.workflow.fetch_catalog(
                    self.catalog,
                    url=entry.navigation_url,
                    on_status=lambda message: self._begin_outgoing_call(message),
                )
            except Exception as exc:
                self.finish_outgoing_call(f"Catalog navigation failed: {_error_message(exc)}")
                return
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
        self.query_one("#feed-body", FeedEntryList).set_selected_index(self.selected_index)
        self.query_one("#status-line", StatusLine).set_message(
            f"Selected {self.feed.entries[self.selected_index].title}"
        )

    def _begin_outgoing_call(self, message: str) -> None:
        self.query_one("#busy-indicator", BusyIndicator).start(message)
        self.query_one("#status-line", StatusLine).set_message(message)

    def _feed_text(self) -> str:
        return FeedEntryList.render_text(
            self.breadcrumbs,
            self.feed.source_url,
            self.feed.updated,
            self.feed.entries,
            self.selected_index,
        )

    def _entry_kind(self, entry: CatalogEntry) -> str:
        if entry.navigation_url is not None:
            return "[Folder]"
        if entry.acquisition_links:
            return "[Book]"
        return "[Entry]"

    def _entry_label(self, entry: CatalogEntry) -> str:
        label = f"{self._entry_kind(entry)} {entry.title}"
        if entry.navigation_url is not None:
            return label
        if entry.authors:
            return f"{label} - {', '.join(entry.authors)}"
        if entry.acquisition_links:
            return f"{label} - Unknown author"
        return label


class EntryScreen(Screen[None]):
    KEY_HINT = "Keys: d download | j/k select | b back | c catalogs | l library"
    BINDINGS = [
        ("d", "download_selected", "Download"),
        ("b", "go_back", "Back"),
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
        yield EntryDetailView(self.entry, selected_index=self.selected_index)
        yield BusyIndicator(id="busy-indicator")
        yield StatusLine("Ready", id="status-line")
        yield KeyHintFooter(self.KEY_HINT)

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
        try:
            await self.workflow.download_acquisition(
                self.catalog,
                self.entry,
                link=self.entry.acquisition_links[index],
                on_status=status_screen.set_status,
                on_progress=lambda progress: status_screen.update_progress(progress),
            )
        except Exception as exc:
            status_screen.set_status(f"Download failed: {_error_message(exc)}")
            return
        status_screen.set_status("Download complete")

    async def action_download_selected(self) -> None:
        await self.download_acquisition(self.selected_index)

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_cursor_down(self) -> None:
        self._move_selection(1)

    def action_cursor_up(self) -> None:
        self._move_selection(-1)

    def _move_selection(self, delta: int) -> None:
        if not self.entry.acquisition_links:
            return
        self.selected_index = max(0, min(len(self.entry.acquisition_links) - 1, self.selected_index + delta))
        self.query_one("#entry-body", EntryDetailView).set_selected_index(self.selected_index)
        link = self.entry.acquisition_links[self.selected_index]
        label = link.title or link.media_type
        self.query_one("#status-line", StatusLine).set_message(f"Selected {label}")

    def _entry_text(self) -> str:
        return EntryDetailView.render_text(self.entry, self.selected_index)


class DownloadStatusScreen(Screen[None]):
    KEY_HINT = "Keys: b back | l library | c catalogs"
    BINDINGS = [
        ("b", "go_back", "Back"),
    ]

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
        yield StatusLine("Ready", id="status-line")
        yield KeyHintFooter(self.KEY_HINT)

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

    def action_go_back(self) -> None:
        if len(self.app.screen_stack) > 1:
            self.app.pop_screen()


class LibraryScreen(Screen[None]):
    KEY_HINT = "Keys: enter preview | j/k select | / search | r refresh | m read | x delete | c catalogs"
    BINDINGS = [
        ("enter", "open_selected", "Open"),
        ("/", "focus_search", "Search"),
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
        self.search_active = False
        self.current_search_query = ""
        if self.library is not None:
            self.books = self.library.list_books()

    def compose(self) -> ComposeResult:
        yield AppShell(area="Library", key_hints=self.KEY_HINT)

    def on_mount(self) -> None:
        replace_region(
            self.query_one("#main-region"),
            Input(placeholder="Search library", disabled=True, id="library-search"),
            LibraryBookList(self.books, selected_index=self.selected_index),
        )
        replace_region(
            self.query_one("#detail-region"),
            StatusLine("Ready", id="status-line"),
        )
        self.app.set_focus(None)
        self.call_after_refresh(lambda: self.app.set_focus(None))

    def action_focus_search(self) -> None:
        search = self.query_one("#library-search", Input)
        search.disabled = False
        self.search_active = True
        self.app.set_focus(search)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "library-search":
            self.apply_search(event.value)
            event.input.disabled = True
            self.search_active = False
            self.app.set_focus(None)

    def apply_search(self, query: str) -> None:
        if self.library is None:
            self._set_status("Library is not available")
            return
        cleaned = query.strip()
        self.current_search_query = cleaned
        self.books = self.library.search_books(LibrarySearch(query=cleaned or None))
        self.selected_index = 0
        self.query_one("#library-body", LibraryBookList).set_books(self.books, self.selected_index)
        self._set_status(f"Search: {cleaned}" if cleaned else "Search cleared")

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

        try:
            self.library.delete_book(book.local_file_path, remove_file=True)
        except Exception as exc:
            self._set_status(f"Delete failed: {_error_message(exc)}")
            return
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
        try:
            preview = extract_epub_preview(book.local_file_path)
        except (ReaderError, OSError) as exc:
            self._set_status(f"Preview failed: {_error_message(exc)}")
            return
        self.app.push_screen(
            EpubReaderScreen(
                preview,
                library=self.library,
                book_path=book.local_file_path,
            )
        )

    def action_open_selected(self) -> None:
        if self.search_active:
            search = self.query_one("#library-search", Input)
            self.apply_search(search.value)
            search.disabled = True
            self.search_active = False
            self.app.set_focus(None)
            return
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
            if self.current_search_query:
                self.books = self.library.search_books(LibrarySearch(query=self.current_search_query))
            else:
                self.books = self.library.list_books()
        if self.selected_index >= len(self.books):
            self.selected_index = max(0, len(self.books) - 1)
        self.query_one("#library-body", LibraryBookList).set_books(self.books, self.selected_index)

    def _set_status(self, message: str) -> None:
        self.query_one("#status-line", StatusLine).set_message(message)

    def _move_selection(self, delta: int) -> None:
        if not self.books:
            return
        self.selected_index = max(0, min(len(self.books) - 1, self.selected_index + delta))
        self.query_one("#library-body", LibraryBookList).set_selected_index(self.selected_index)
        self._set_status(f"Selected {self.books[self.selected_index].title}")

    def _library_text(self) -> str:
        return LibraryBookList.render_text(self.books, self.selected_index)


def _error_message(error: Exception) -> str:
    return str(error) or error.__class__.__name__


class EpubPreviewScreen(Screen[None]):
    KEY_HINT = "Keys: c catalogs | l library | q quit"

    def __init__(self, preview: EpubPreview, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.preview = preview

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine(self._preview_text(), id="preview-body")
        yield KeyHintFooter(self.KEY_HINT)

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
    KEY_HINT = "Keys: c catalogs | l library | q quit"

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
        yield KeyHintFooter(self.KEY_HINT)

    def _auth_text(self) -> str:
        name = getattr(self.catalog, "name", "Catalog")
        username = self.credentials["username"] or "(none)"
        password_text = "(set)" if self.credentials["password"] else "(none)"
        return f"{name}\nUsername: {username}\nPassword: {password_text}"
