from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ebooklib import epub

from epub_tui.app import EpubTuiApp
from epub_tui.catalog.client import CatalogFetchError
from epub_tui.catalog.models import AcquisitionLink, CatalogEntry, CatalogFeed
from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.downloads import DownloadError, DownloadProgress
from epub_tui.library import BookRecord, LibraryRepository
from epub_tui.reader import EpubOutlineItem, EpubPreview, EpubSection
from epub_tui.tui.reader import EpubReaderScreen
from epub_tui.tui.screens import (
    CatalogAuthScreen,
    CatalogsScreen,
    DownloadStatusScreen,
    EntryScreen,
    EpubPreviewScreen,
    FeedScreen,
    LibraryScreen,
)


class FakeWorkflow:
    def __init__(
        self,
        feed: CatalogFeed | None = None,
        download_path: Path | None = None,
        download_error: Exception | None = None,
    ) -> None:
        self.feed = feed
        self.download_path = download_path or Path("downloaded.epub")
        self.download_error = download_error
        self.fetch_statuses: list[str] = []
        self.download_statuses: list[str] = []
        self.downloads: list[tuple[CatalogConfig, CatalogEntry, AcquisitionLink | None]] = []
        self.fetch_urls: list[str | None] = []

    async def fetch_catalog(
        self,
        catalog: CatalogConfig,
        url: str | None = None,
        on_status: Any | None = None,
    ) -> CatalogFeed:
        self.fetch_urls.append(url)
        if on_status is not None:
            on_status("Fetching catalog...")
            self.fetch_statuses.append("Fetching catalog...")
        if self.feed is None:
            raise AssertionError("FakeWorkflow.feed is required")
        if on_status is not None:
            on_status("Catalog loaded")
            self.fetch_statuses.append("Catalog loaded")
        return self.feed

    async def download_acquisition(
        self,
        catalog: CatalogConfig,
        entry: CatalogEntry,
        link: AcquisitionLink | None = None,
        on_status: Any | None = None,
        on_progress: Any | None = None,
    ) -> Path:
        self.downloads.append((catalog, entry, link))
        if on_status is not None:
            on_status("Starting download...")
            self.download_statuses.append("Starting download...")
        if on_progress is not None:
            on_progress(DownloadProgress(bytes_received=10, total_bytes=10))
        if self.download_error is not None:
            raise self.download_error
        if on_status is not None:
            on_status("Download complete")
            self.download_statuses.append("Download complete")
        return self.download_path


class MappingWorkflow(FakeWorkflow):
    def __init__(self, feeds: dict[str | None, CatalogFeed]) -> None:
        super().__init__()
        self.feeds = feeds

    async def fetch_catalog(
        self,
        catalog: CatalogConfig,
        url: str | None = None,
        on_status: Any | None = None,
    ) -> CatalogFeed:
        self.fetch_urls.append(url)
        if on_status is not None:
            on_status("Fetching catalog...")
            self.fetch_statuses.append("Fetching catalog...")
        return self.feeds[url]


class FailingFetchWorkflow(FakeWorkflow):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    async def fetch_catalog(
        self,
        catalog: CatalogConfig,
        url: str | None = None,
        on_status: Any | None = None,
    ) -> CatalogFeed:
        self.fetch_urls.append(url)
        if on_status is not None:
            on_status("Fetching catalog...")
            self.fetch_statuses.append("Fetching catalog...")
        raise self.error


def _entry() -> CatalogEntry:
    return CatalogEntry(
        title="Interesting Book",
        identifier="urn:book:interesting",
        updated="2026-05-30",
        authors=["Ada Lovelace"],
        summary="A small but useful book.",
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/interesting.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            ),
            AcquisitionLink(
                href="https://example.test/books/interesting.pdf",
                relation="http://opds-spec.org/acquisition",
                media_type="application/pdf",
                title="PDF",
            ),
        ],
    )


def _feed() -> CatalogFeed:
    return CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated="2026-05-30",
        entries=[_entry()],
    )


def _navigation_entry() -> CatalogEntry:
    return CatalogEntry(
        title="Fiction",
        identifier="urn:nav:fiction",
        updated="2026-05-30",
        navigation_url="https://example.test/opds/fiction",
    )


def _write_preview_epub(epub_path: Path, title: str) -> None:
    book = epub.EpubBook()
    book.set_identifier(title)
    book.set_title(title)
    book.set_language("en")
    chapter = epub.EpubHtml(title="Chapter One", file_name="chapter.xhtml", lang="en")
    chapter.content = b"<html><body><h1>Chapter One</h1><p>Readable text.</p></body></html>"
    book.add_item(chapter)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)


def _book(tmp_path: Path, *, title: str = "Interesting Book", is_read: bool = False) -> BookRecord:
    book_path = tmp_path / "books" / f"{title}.epub"
    book_path.parent.mkdir(exist_ok=True)
    _write_preview_epub(book_path, title)
    return BookRecord(
        title=title,
        authors=["Ada Lovelace"],
        identifiers=["urn:book:interesting"],
        source_catalog="Example",
        source_entry_url="https://example.test/opds/book",
        acquisition_url="https://example.test/books/interesting.epub",
        media_type="application/epub+zip",
        cover_image_url=None,
        cover_image_path=None,
        local_file_path=book_path,
        is_read=is_read,
    )


@pytest.mark.asyncio
async def test_feed_screen_renders_feed_entries_and_busy_states() -> None:
    feed = CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated="2026-05-30",
        entries=[_navigation_entry(), _entry()],
    )
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(FeedScreen(feed))
        screen = app.screen

        rendered = str(screen.query_one("#feed-body").renderable)
        assert "Example Feed" in rendered
        assert "Catalog > Example Feed" in rendered
        assert "[Folder] Fiction" in rendered
        assert "[Folder] Fiction - Unknown author" not in rendered
        assert "[Book] Interesting Book" in rendered
        assert "Interesting Book" in rendered

        screen.begin_fetch("Fetching feed")
        assert "Fetching feed" in str(screen.query_one("#busy-indicator").renderable)
        screen.begin_refresh("Refreshing feed")
        assert "Refreshing feed" in str(screen.query_one("#busy-indicator").renderable)
        screen.begin_navigation("Opening next page")
        assert "Opening next page" in str(screen.query_one("#busy-indicator").renderable)


@pytest.mark.asyncio
async def test_feed_screen_uses_entry_row_widgets_for_selection() -> None:
    feed = CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated="2026-05-30",
        entries=[_navigation_entry(), _entry()],
    )
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed))

        rows = list(app.screen.query("#feed-body .feed-entry-row"))
        assert [row.id for row in rows] == ["feed-entry-0", "feed-entry-1"]
        assert rows[0].has_class("kind-folder")
        assert rows[1].has_class("kind-book")
        assert rows[0].has_class("selected")
        assert not rows[1].has_class("selected")

        await pilot.press("j")

        rows = list(app.screen.query("#feed-body .feed-entry-row"))
        assert not rows[0].has_class("selected")
        assert rows[1].has_class("selected")


@pytest.mark.asyncio
async def test_catalog_screen_opens_feed_through_workflow() -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(feed=_feed())
    app = EpubTuiApp(
        config=AppConfig(library_path=Path("books"), catalogs=[catalog]),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await app.screen.open_catalog(0)
        await pilot.pause()

        assert isinstance(app.screen, FeedScreen)
        assert workflow.fetch_statuses == ["Fetching catalog...", "Catalog loaded"]
        assert "Example Feed" in str(app.screen.query_one("#feed-body").renderable)


@pytest.mark.asyncio
async def test_catalog_screen_reports_fetch_failure_without_opening_feed() -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FailingFetchWorkflow(CatalogFetchError("network unavailable"))
    app = EpubTuiApp(
        config=AppConfig(library_path=Path("books"), catalogs=[catalog]),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await app.screen.open_catalog(0)
        await pilot.pause()

        assert isinstance(app.screen, CatalogsScreen)
        assert "Catalog failed: network unavailable" in str(
            app.screen.query_one("#status-line").renderable
        )
        assert "Fetching catalog" not in str(app.screen.query_one("#busy-indicator").renderable)


@pytest.mark.asyncio
async def test_catalog_screen_enter_binding_opens_feed_through_workflow() -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(feed=_feed())
    app = EpubTuiApp(
        config=AppConfig(library_path=Path("books"), catalogs=[catalog]),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await pilot.press("enter")

        assert isinstance(app.screen, FeedScreen)
        assert workflow.fetch_statuses == ["Fetching catalog...", "Catalog loaded"]


@pytest.mark.asyncio
async def test_catalog_screen_selection_moves_before_opening() -> None:
    catalogs = [
        CatalogConfig(name="First", url="https://first.test/opds"),
        CatalogConfig(name="Second", url="https://second.test/opds"),
    ]
    workflow = FakeWorkflow(feed=_feed())
    app = EpubTuiApp(
        config=AppConfig(library_path=Path("books"), catalogs=catalogs),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await pilot.press("j")

        assert "> Second" in str(app.screen.query_one("#catalog-list").renderable)
        await pilot.press("enter")

        assert isinstance(app.screen, FeedScreen)
        assert workflow.fetch_urls == [None]
        assert app.screen.catalog == catalogs[1]


@pytest.mark.asyncio
async def test_feed_screen_opens_entry_details() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(_feed()))
        await app.screen.open_entry(0)
        await pilot.pause()

        assert isinstance(app.screen, EntryScreen)
        assert "Interesting Book" in str(app.screen.query_one("#entry-body").renderable)


@pytest.mark.asyncio
async def test_feed_screen_enter_binding_opens_entry_details() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(_feed()))
        await pilot.press("enter")

        assert isinstance(app.screen, EntryScreen)


@pytest.mark.asyncio
async def test_feed_screen_selection_moves_before_opening_entry() -> None:
    feed = CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_navigation_entry(), _entry()],
    )
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed))
        await pilot.press("j")

        assert "> 2. [Book] Interesting Book" in str(app.screen.query_one("#feed-body").renderable)
        await pilot.press("enter")

        assert isinstance(app.screen, EntryScreen)
        assert "Interesting Book" in str(app.screen.query_one("#entry-body").renderable)


@pytest.mark.asyncio
async def test_feed_screen_navigation_entry_fetches_next_feed() -> None:
    next_feed = CatalogFeed(
        title="Fiction Feed",
        source_url="https://example.test/opds/fiction",
        updated=None,
        entries=[_entry()],
    )
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(feed=next_feed)
    feed = CatalogFeed(
        title="Root Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_navigation_entry()],
    )
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.press("enter")

        assert isinstance(app.screen, FeedScreen)
        assert app.screen.feed.title == "Fiction Feed"
        assert "Root Feed > Fiction Feed" in str(app.screen.query_one("#feed-body").renderable)
        assert workflow.fetch_urls == ["https://example.test/opds/fiction"]


@pytest.mark.asyncio
async def test_feed_screen_reports_navigation_fetch_failure_without_opening_feed() -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FailingFetchWorkflow(CatalogFetchError("parse failed"))
    feed = CatalogFeed(
        title="Root Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_navigation_entry()],
    )
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        original_screen = app.screen
        await pilot.press("enter")
        await pilot.pause()

        assert app.screen is original_screen
        assert isinstance(app.screen, FeedScreen)
        assert app.screen.feed.title == "Root Feed"
        assert "Catalog navigation failed: parse failed" in str(
            app.screen.query_one("#status-line").renderable
        )
        assert "Fetching catalog" not in str(app.screen.query_one("#busy-indicator").renderable)
        assert workflow.fetch_urls == ["https://example.test/opds/fiction"]


@pytest.mark.asyncio
async def test_feed_screen_back_binding_returns_to_parent_feed() -> None:
    next_feed = CatalogFeed(
        title="Fiction Feed",
        source_url="https://example.test/opds/fiction",
        updated=None,
        entries=[_entry()],
    )
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(feed=next_feed)
    feed = CatalogFeed(
        title="Root Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_navigation_entry()],
    )
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.press("enter")
        assert isinstance(app.screen, FeedScreen)
        assert app.screen.feed.title == "Fiction Feed"

        await pilot.press("b")

        assert isinstance(app.screen, FeedScreen)
        assert app.screen.feed.title == "Root Feed"


@pytest.mark.asyncio
async def test_entry_screen_renders_cover_fallback_and_all_acquisitions() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(EntryScreen(_entry()))
        screen = app.screen
        rendered = str(screen.query_one("#entry-body").renderable)
        cover = str(screen.query_one("#cover-display").renderable)

        screen.begin_download("Preparing download")
        busy = str(screen.query_one("#busy-indicator").renderable)

    assert "Interesting Book" in rendered
    assert "A small but useful book." in rendered
    assert "application/epub+zip" in rendered
    assert "application/pdf" in rendered
    assert "Ada Lovelace" in cover
    assert "Preparing download" in busy


@pytest.mark.asyncio
async def test_entry_screen_downloads_acquisition_through_workflow(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(download_path=tmp_path / "Interesting Book.pdf")
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry(), catalog=catalog, workflow=workflow))
        await app.screen.download_acquisition(1)
        await pilot.pause()

        assert isinstance(app.screen, DownloadStatusScreen)
        assert workflow.downloads[0][2] == _entry().acquisition_links[1]
        assert "Download complete" in str(app.screen.query_one("#download-status").renderable)
        assert "Keys:" in str(app.screen.query_one("#status-line").renderable)


@pytest.mark.asyncio
async def test_entry_screen_download_binding_uses_workflow(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(download_path=tmp_path / "Interesting Book.epub")
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry(), catalog=catalog, workflow=workflow))
        await pilot.press("d")

        assert isinstance(app.screen, DownloadStatusScreen)
        assert workflow.downloads[0][2] == _entry().acquisition_links[0]


@pytest.mark.asyncio
async def test_download_status_back_returns_to_entry_screen(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(download_path=tmp_path / "Interesting Book.epub")
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry(), catalog=catalog, workflow=workflow))
        await pilot.press("d")
        assert isinstance(app.screen, DownloadStatusScreen)

        await pilot.press("b")

        assert isinstance(app.screen, EntryScreen)


@pytest.mark.asyncio
async def test_download_status_library_binding_opens_library(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(download_path=tmp_path / "Interesting Book.epub")
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    app = EpubTuiApp(config=AppConfig(library_path=tmp_path), workflow=workflow, library=repo)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry(), catalog=catalog, workflow=workflow))
        await pilot.press("d")
        assert isinstance(app.screen, DownloadStatusScreen)

        await pilot.press("l")

        assert isinstance(app.screen, LibraryScreen)


@pytest.mark.asyncio
async def test_entry_screen_download_error_stays_on_status_screen(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(
        download_path=tmp_path / "Interesting Book.epub",
        download_error=DownloadError("Download destination already exists"),
    )
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry(), catalog=catalog, workflow=workflow))
        await pilot.press("d")
        await pilot.pause()

        assert isinstance(app.screen, DownloadStatusScreen)
        assert "Download failed: Download destination already exists" in str(
            app.screen.query_one("#download-status").renderable
        )


@pytest.mark.asyncio
async def test_entry_screen_download_filesystem_error_stays_on_status_screen(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(
        download_path=tmp_path / "Interesting Book.epub",
        download_error=OSError("disk full"),
    )
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry(), catalog=catalog, workflow=workflow))
        await pilot.press("d")
        await pilot.pause()

        assert isinstance(app.screen, DownloadStatusScreen)
        assert "Download failed: disk full" in str(
            app.screen.query_one("#download-status").renderable
        )


@pytest.mark.asyncio
async def test_entry_screen_selection_moves_before_downloading(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(download_path=tmp_path / "Interesting Book.pdf")
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry(), catalog=catalog, workflow=workflow))
        await pilot.press("j")

        assert "> PDF" in str(app.screen.query_one("#entry-body").renderable)
        await pilot.press("d")

        assert isinstance(app.screen, DownloadStatusScreen)
        assert workflow.downloads[0][2] == _entry().acquisition_links[1]


@pytest.mark.asyncio
async def test_download_status_screen_renders_known_and_unknown_progress() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(DownloadStatusScreen(status="Waiting"))
        screen = app.screen

        assert "Waiting" in str(screen.query_one("#download-status").renderable)

        screen.update_progress(DownloadProgress(bytes_received=50, total_bytes=100), "Downloading")
        assert "50%" in str(screen.query_one("#download-progress").renderable)
        assert "Downloading" in str(screen.query_one("#download-status").renderable)

        screen.update_progress(DownloadProgress(bytes_received=2048, total_bytes=None), "Still downloading")
        assert "indeterminate" in str(screen.query_one("#download-progress").renderable)


@pytest.mark.asyncio
async def test_library_screen_renders_books_and_updates_repository(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, is_read=False))
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(LibraryScreen(library=repo))
        screen = app.screen
        assert "Interesting Book" in str(screen.query_one("#library-body").renderable)
        assert "Unread" in str(screen.query_one("#library-body").renderable)

        screen.action_toggle_read()
        assert repo.list_books()[0].is_read is True
        assert "Read" in str(screen.query_one("#library-body").renderable)

        screen.action_delete_book()
        assert repo.list_books() == []
        assert "No downloaded books" in str(screen.query_one("#library-body").renderable)


@pytest.mark.asyncio
async def test_library_screen_uses_book_row_widgets_for_selection(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=False))
    repo.add_book(_book(tmp_path, title="Foundation", is_read=True))
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))

        rows = list(app.screen.query("#library-body .library-book-row"))
        assert [row.id for row in rows] == ["library-book-0", "library-book-1"]
        assert rows[0].has_class("state-unread")
        assert rows[1].has_class("state-read")
        assert rows[0].has_class("selected")
        assert not rows[1].has_class("selected")
        assert "Ada Lovelace" in str(rows[0].renderable)
        assert "application/epub+zip" in str(rows[0].renderable)
        assert str(tmp_path) in str(rows[0].renderable)

        await pilot.press("j")

        rows = list(app.screen.query("#library-body .library-book-row"))
        assert not rows[0].has_class("selected")
        assert rows[1].has_class("selected")


@pytest.mark.asyncio
async def test_library_screen_delete_failure_stays_on_library_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, is_read=False))

    def fail_delete(*args: object, **kwargs: object) -> None:
        raise PermissionError("locked")

    monkeypatch.setattr(repo, "delete_book", fail_delete)
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(LibraryScreen(library=repo))
        screen = app.screen
        screen.action_delete_book()

        assert isinstance(app.screen, LibraryScreen)
        assert "Interesting Book" in str(screen.query_one("#library-body").renderable)
        assert "Delete failed: locked" in str(screen.query_one("#status-line").renderable)


@pytest.mark.asyncio
async def test_library_screen_selects_and_opens_epub_reader(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, is_read=False))
    repo.add_book(_book(tmp_path, title="Second Book", is_read=False))
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.press("j")

        assert "> 2. Second Book" in str(app.screen.query_one("#library-body").renderable)
        assert app.screen.selected_book is not None
        assert app.screen.selected_book.title == "Second Book"

        await pilot.press("enter")

        assert isinstance(app.screen, EpubReaderScreen)


@pytest.mark.asyncio
async def test_library_screen_reports_epub_preview_failure_without_opening_reader(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    stale_book = _book(tmp_path, is_read=False)
    stale_book.local_file_path.unlink()
    repo.add_book(stale_book)
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.press("enter")
        await pilot.pause()

        assert isinstance(app.screen, LibraryScreen)
        status = str(app.screen.query_one("#status-line").renderable)
        assert "Preview failed:" in status
        assert "Could not read EPUB preview" in status


@pytest.mark.asyncio
async def test_library_screen_refresh_binding_loads_new_books(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        assert "No downloaded books" in str(app.screen.query_one("#library-body").renderable)

        repo.add_book(_book(tmp_path, is_read=False))
        await pilot.press("r")

        assert "Interesting Book" in str(app.screen.query_one("#library-body").renderable)
        assert "Library refreshed" in str(app.screen.query_one("#status-line").renderable)


@pytest.mark.asyncio
async def test_library_screen_filters_books_by_search_text(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=False))
    repo.add_book(_book(tmp_path, title="Foundation", is_read=True))
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.press("/")
        app.screen.query_one("#library-search").value = "dune"
        await pilot.press("enter")

        rendered = str(app.screen.query_one("#library-body").renderable)
        assert "Dune" in rendered
        assert "Foundation" not in rendered
        assert "Search: dune" in str(app.screen.query_one("#status-line").renderable)


@pytest.mark.asyncio
async def test_library_screen_preserves_search_during_library_actions(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=False))
    repo.add_book(_book(tmp_path, title="Dune Messiah", is_read=False))
    repo.add_book(_book(tmp_path, title="Foundation", is_read=False))
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.press("/")
        app.screen.query_one("#library-search").value = "dune"
        await pilot.press("enter")

        await pilot.press("r")

        rendered = str(app.screen.query_one("#library-body").renderable)
        assert "Dune" in rendered
        assert "Dune Messiah" in rendered
        assert "Foundation" not in rendered
        assert "Library refreshed" in str(app.screen.query_one("#status-line").renderable)

        app.screen.action_toggle_read()

        rendered = str(app.screen.query_one("#library-body").renderable)
        assert "Dune" in rendered
        assert "Dune Messiah" in rendered
        assert "Foundation" not in rendered
        assert "Read status updated" in str(app.screen.query_one("#status-line").renderable)

        app.screen.selected_index = 1
        app.screen.action_delete_book()

        rendered = str(app.screen.query_one("#library-body").renderable)
        assert "Dune" in rendered
        assert "Dune Messiah" not in rendered
        assert "Foundation" not in rendered
        assert app.screen.selected_index == 0
        assert "Book deleted" in str(app.screen.query_one("#status-line").renderable)

        await pilot.press("/")
        app.screen.query_one("#library-search").value = ""
        await pilot.press("enter")

        rendered = str(app.screen.query_one("#library-body").renderable)
        assert "Dune" in rendered
        assert "Foundation" in rendered
        assert "Search cleared" in str(app.screen.query_one("#status-line").renderable)


@pytest.mark.asyncio
async def test_library_screen_rows_show_format_catalog_and_progress(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=True))
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(LibraryScreen(library=repo))
        rendered = str(app.screen.query_one("#library-body").renderable)

        assert "application/epub+zip" in rendered
        assert "Example" in rendered
        assert "Read" in rendered


@pytest.mark.asyncio
async def test_primary_screens_show_key_hints(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(CatalogsScreen(AppConfig(library_path=tmp_path)))
        assert "Keys:" in str(app.screen.query_one("#status-line").renderable)

        await app.push_screen(FeedScreen(_feed()))
        assert "Keys:" in str(app.screen.query_one("#status-line").renderable)

        await app.push_screen(EntryScreen(_entry()))
        assert "Keys:" in str(app.screen.query_one("#status-line").renderable)

        await app.push_screen(LibraryScreen(library=repo))
        assert "Keys:" in str(app.screen.query_one("#status-line").renderable)


@pytest.mark.asyncio
async def test_app_library_bindings_delegate_to_active_library_screen(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, is_read=False))
    config = AppConfig(library_path=tmp_path)
    app = EpubTuiApp(config=config, library=repo)

    async with app.run_test() as pilot:
        app.action_show_library()
        await pilot.pause()
        assert isinstance(app.screen, LibraryScreen)

        app.action_toggle_read()
        assert repo.list_books()[0].is_read is True

        app.action_delete_book()
        assert repo.list_books() == []


@pytest.mark.asyncio
async def test_app_catalog_binding_returns_from_library_to_catalogs(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    config = AppConfig(library_path=tmp_path, catalogs=[catalog])
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    app = EpubTuiApp(config=config, library=repo)

    async with app.run_test() as pilot:
        app.action_show_library()
        await pilot.pause()
        assert isinstance(app.screen, LibraryScreen)

        app.action_show_catalogs()
        await pilot.pause()

        assert isinstance(app.screen, CatalogsScreen)
        assert "Example" in str(app.screen.query_one("#catalog-list").renderable)


@pytest.mark.asyncio
async def test_app_add_catalog_binding_opens_catalogs_with_form_visible(tmp_path: Path) -> None:
    config = AppConfig(library_path=tmp_path, catalogs=[])
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    app = EpubTuiApp(config=config, library=repo)

    async with app.run_test() as pilot:
        app.action_show_library()
        await pilot.pause()

        app.action_add_catalog()
        await pilot.pause()

        assert isinstance(app.screen, CatalogsScreen)
        assert app.screen.query_one("#catalog-form").display is True


@pytest.mark.asyncio
async def test_catalog_screen_hides_add_form_until_requested(tmp_path: Path) -> None:
    config = AppConfig(library_path=tmp_path, catalogs=[])
    app = EpubTuiApp(config=config)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, CatalogsScreen)
        assert screen.query_one("#catalog-form").display is False

        screen.action_toggle_add_catalog()

        assert screen.query_one("#catalog-form").display is True


@pytest.mark.asyncio
async def test_feed_screen_can_drill_down_multiple_navigation_levels() -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    root_feed = CatalogFeed(
        title="Root",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_navigation_entry()],
    )
    group_feed = CatalogFeed(
        title="Fiction",
        source_url="https://example.test/opds/fiction",
        updated=None,
        entries=[
            CatalogEntry(
                title="Classics",
                identifier="urn:nav:classics",
                updated=None,
                navigation_url="https://example.test/opds/fiction/classics",
            )
        ],
    )
    books_feed = CatalogFeed(
        title="Classics",
        source_url="https://example.test/opds/fiction/classics",
        updated=None,
        entries=[_entry()],
    )
    workflow = MappingWorkflow(
        {
            None: root_feed,
            "https://example.test/opds/fiction": group_feed,
            "https://example.test/opds/fiction/classics": books_feed,
        }
    )
    app = EpubTuiApp(
        config=AppConfig(library_path=Path("books"), catalogs=[catalog]),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await app.screen.open_catalog(0)
        await pilot.pause()
        await app.screen.open_entry(0)
        await pilot.pause()
        await app.screen.open_entry(0)
        await pilot.pause()

        assert isinstance(app.screen, FeedScreen)
        assert app.screen.feed.title == "Classics"
        assert "Interesting Book" in str(app.screen.query_one("#feed-body").renderable)
        assert workflow.fetch_urls == [
            None,
            "https://example.test/opds/fiction",
            "https://example.test/opds/fiction/classics",
        ]


@pytest.mark.asyncio
async def test_epub_preview_screen_renders_plain_text_preview() -> None:
    preview = EpubPreview(
        title="Preview Title",
        outline=(EpubOutlineItem(title="Chapter One", section_index=0),),
        sections=(EpubSection(heading="Chapter One", text="Plain text body."),),
    )
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(EpubPreviewScreen(preview))
        rendered = str(app.screen.query_one("#preview-body").renderable)

    assert "Preview Title" in rendered
    assert "Chapter One" in rendered
    assert "Plain text body." in rendered


@pytest.mark.asyncio
async def test_catalog_auth_screen_redacts_password() -> None:
    catalog = CatalogConfig(
        name="Private Catalog",
        url="https://example.test/opds",
        auth={"username": "reader", "password": "secret-password"},
    )
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(CatalogAuthScreen(catalog))
        screen = app.screen
        rendered = str(screen.query_one("#auth-body").renderable)

    assert "Private Catalog" in rendered
    assert "reader" in rendered
    assert "secret-password" not in rendered
    assert screen.credentials == {"username": "reader", "password": "secret-password"}
