from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest
from ebooklib import epub
from textual.containers import VerticalScroll
from textual.widgets import Footer

from shelfline.app import ShelflineApp
from shelfline.catalog.client import CatalogFetchError
from shelfline.catalog.models import AcquisitionLink, CatalogEntry, CatalogFeed
from shelfline.config import (
    AppConfig,
    AppPreferences,
    CatalogConfig,
    CoverPreferences,
    ReaderPreferences,
)
from shelfline.downloads import DownloadError, DownloadProgress
from shelfline.library import BookRecord, LibraryRepository
from shelfline.reader import EpubOutlineItem, EpubPreview, EpubSection
from shelfline.tui.layout import KeyHintFooter
from shelfline.tui.reader import EpubReaderScreen
from shelfline.tui.screens import (
    CatalogAuthScreen,
    CatalogsScreen,
    DownloadStatusScreen,
    EntryScreen,
    EpubPreviewScreen,
    FeedScreen,
    LibraryScreen,
    SetupScreen,
)
from shelfline.tui.theme import (
    BOOK_LABEL,
    DOWNLOADS_LABEL,
    FOLDER_LABEL,
    LOCAL_PATH_LABEL,
    OPEN_PREVIEW_LABEL,
    READ_LABEL,
    UNREAD_LABEL,
    glyph,
)
from shelfline.tui.widgets import CatalogList, CoverDisplay, FeedEntryList, LibraryBookList


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
        self.catalog_cover_path: Path | None = None
        self.book_cover_path: Path | None = None
        self.catalog_cover_requests: list[tuple[CatalogConfig, CatalogEntry]] = []
        self.book_cover_requests: list[BookRecord] = []

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

    async def cache_catalog_entry_cover(
        self,
        catalog: CatalogConfig,
        entry: CatalogEntry,
    ) -> Path | None:
        self.catalog_cover_requests.append((catalog, entry))
        return self.catalog_cover_path

    async def cache_book_remote_cover(self, book: BookRecord) -> BookRecord:
        self.book_cover_requests.append(book)
        if self.book_cover_path is None:
            return book
        assert hasattr(self, "library")
        self.library.update_cover_cache(book.local_file_path, self.book_cover_path, "cached")
        return self.library.list_books()[0]


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


def _selector_block(css: str, selector: str) -> str:
    match = re.search(
        rf"(?ms)^\s*{re.escape(selector)}\s*\{{(?P<body>.*?)^\s*\}}",
        css,
    )
    assert match is not None, f"Missing CSS selector {selector}"
    return match.group("body")


def test_catalog_detail_styles_constrain_cover_area() -> None:
    css = Path("src/shelfline/tui/app.tcss").read_text(encoding="utf-8")
    assert _selector_block(css, ".catalog-entry-detail")
    cover_box = _selector_block(css, ".catalog-cover-box")
    cover_display = _selector_block(css, ".catalog-cover-display")
    cover_image = _selector_block(css, ".catalog-cover-display .cover-image")
    assert _selector_block(css, ".catalog-detail-hint")

    assert "height:" in cover_box
    assert "max-height:" in cover_box
    assert "height:" in cover_display
    assert "max-height:" in cover_display
    assert "width: auto;" in cover_image
    assert "height: auto;" in cover_image


def _navigation_entry() -> CatalogEntry:
    return CatalogEntry(
        title="Fiction",
        identifier="urn:nav:fiction",
        updated="2026-05-30",
        navigation_url="https://example.test/opds/fiction",
    )


def _entry_without_downloads() -> CatalogEntry:
    return CatalogEntry(
        title="Unavailable Book",
        identifier="urn:book:unavailable",
        updated="2026-05-31",
        authors=["Grace Hopper"],
        summary="A listed book without current downloads.",
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


def _visible_library_detail_text(screen: Any) -> str:
    return "\n".join(
        str(line.render())
        for line in screen.query("#library-detail Static")
        if line.display
    )


@pytest.mark.asyncio
async def test_feed_screen_renders_feed_entries_and_busy_states() -> None:
    feed = CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated="2026-05-30",
        entries=[_navigation_entry(), _entry()],
    )
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(FeedScreen(feed))
        screen = app.screen

        rendered = str(screen.query_one("#feed-body").renderable)
        assert "Example Feed" in rendered
        assert "Catalog > Example Feed" in rendered
        assert f"{FOLDER_LABEL.text} Fiction" in rendered
        assert f"{FOLDER_LABEL.text} Fiction - Unknown author" not in rendered
        assert f"{BOOK_LABEL.text} Interesting Book" in rendered
        assert "Interesting Book" in rendered

        screen.begin_fetch("Fetching feed")
        assert "Fetching feed" in str(screen.query_one("#busy-indicator").renderable)
        screen.begin_refresh("Refreshing feed")
        assert "Refreshing feed" in str(screen.query_one("#busy-indicator").renderable)
        screen.begin_navigation("Opening next page")
        assert "Opening next page" in str(screen.query_one("#busy-indicator").renderable)


@pytest.mark.asyncio
async def test_feed_screen_uses_custom_key_hint_footer() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(FeedScreen(_feed()))

        footer = app.screen.query_one("#key-hints", KeyHintFooter)
        assert FeedScreen.KEY_HINT in str(footer.render())
        assert list(app.screen.query(Footer)) == []


@pytest.mark.asyncio
async def test_feed_screen_uses_entry_row_widgets_for_selection() -> None:
    feed = CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated="2026-05-30",
        entries=[_navigation_entry(), _entry()],
    )
    app = ShelflineApp(config=None)

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
async def test_feed_screen_renders_selected_book_in_detail_pane() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(_feed()))
        await pilot.pause()
        rendered = str(app.screen.query_one("#catalog-entry-detail").renderable)

    assert "Interesting Book" in rendered
    assert "Ada Lovelace" in rendered
    assert "A small but useful book." in rendered
    assert "EPUB" in rendered
    assert "PDF" in rendered
    assert "d download" in rendered


@pytest.mark.asyncio
async def test_feed_screen_renders_folder_detail_without_book_noise() -> None:
    feed = CatalogFeed(
        title="Root Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_navigation_entry()],
    )
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed))
        await pilot.pause()
        rendered = str(app.screen.query_one("#catalog-entry-detail").renderable)

    assert "Fiction" in rendered
    assert "Enter open" in rendered
    assert "Unknown author" not in rendered
    assert "Cover" not in rendered
    assert "download" not in rendered.lower()


@pytest.mark.asyncio
async def test_feed_screen_renders_book_without_acquisitions_as_unavailable() -> None:
    feed = CatalogFeed(
        title="Root Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_entry_without_downloads()],
    )
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed))
        await pilot.pause()
        rendered = str(app.screen.query_one("#catalog-entry-detail").renderable)

    assert "Unavailable Book" in rendered
    assert "No downloads available" in rendered
    assert "Enter open" not in rendered


@pytest.mark.asyncio
async def test_feed_screen_downloads_selected_book_with_d_key(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    selected_entry = _entry()
    selected_link = selected_entry.best_epub_link()
    assert selected_link is not None
    feed = CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated="2026-05-30",
        entries=[_navigation_entry(), selected_entry],
    )
    workflow = FakeWorkflow(download_path=tmp_path / "Interesting Book.epub")
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.press("j")
        await pilot.press("d")

        assert isinstance(app.screen, DownloadStatusScreen)
        assert workflow.downloads == [(catalog, selected_entry, selected_link)]
        assert "Download complete" in str(app.screen.query_one("#download-status").renderable)


@pytest.mark.asyncio
async def test_feed_screen_download_key_reports_no_download_for_folder() -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow()
    feed = CatalogFeed(
        title="Root Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_navigation_entry()],
    )
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.press("d")

        assert isinstance(app.screen, FeedScreen)
        assert workflow.downloads == []
        assert "Selected entry has no downloads" in str(
            app.screen.query_one("#status-line").renderable
        )


@pytest.mark.asyncio
async def test_feed_screen_many_entries_use_contiguous_scrollable_rows() -> None:
    entries = [
        CatalogEntry(
            title=f"Visible Book {index + 1:02d}",
            identifier=f"urn:book:{index + 1}",
            updated=None,
            authors=[f"Author {index + 1:02d}"],
            acquisition_links=[
                AcquisitionLink(
                    href=f"https://example.test/books/{index + 1}.epub",
                    relation="http://opds-spec.org/acquisition",
                    media_type="application/epub+zip",
                    title="EPUB",
                )
            ],
        )
        for index in range(28)
    ]
    feed = CatalogFeed(
        title="Long Feed",
        source_url="https://example.test/opds/long",
        updated=None,
        entries=entries,
    )
    app = ShelflineApp(config=None)

    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(FeedScreen(feed))
        await pilot.pause()

        feed_body = app.screen.query_one("#feed-body")
        rows = list(app.screen.query("#feed-body .feed-entry-row"))

        assert isinstance(feed_body, FeedEntryList)
        assert isinstance(feed_body, VerticalScroll)
        assert [row.id for row in rows[:6]] == [
            "feed-entry-0",
            "feed-entry-1",
            "feed-entry-2",
            "feed-entry-3",
            "feed-entry-4",
            "feed-entry-5",
        ]
        assert [str(row.query_one(".row-index").render()) for row in rows[:6]] == [
            "1.",
            "2.",
            "3.",
            "4.",
            "5.",
            "6.",
        ]
        assert all(row.styles.margin.top == 0 for row in rows)
        assert all(row.region.height > 0 for row in rows[:3])
        assert feed_body.max_scroll_y > 0

        await pilot.press(*(["j"] * 20))
        await pilot.pause()

        rows = list(app.screen.query("#feed-body .feed-entry-row"))
        selected_row = rows[20]
        assert selected_row.has_class("selected")
        assert str(selected_row.query_one(".row-marker").render()) == ">"
        assert selected_row.region.height > 0
        assert feed_body.scroll_y > 0
        assert feed_body.region.y <= selected_row.region.y
        assert selected_row.region.y + selected_row.region.height <= feed_body.region.y + feed_body.region.height


@pytest.mark.asyncio
async def test_catalog_screen_opens_feed_through_workflow() -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(feed=_feed())
    app = ShelflineApp(
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
    app = ShelflineApp(
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
    app = ShelflineApp(
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
    app = ShelflineApp(
        config=AppConfig(library_path=Path("books"), catalogs=catalogs),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await pilot.press("j")

        assert "> 2. Second" in str(app.screen.query_one("#catalog-list").renderable)
        rows = list(app.screen.query("#catalog-list .catalog-row"))
        assert not rows[0].has_class("selected")
        assert rows[1].has_class("selected")
        assert "Second" in str(app.screen.query_one("#status-line").renderable)
        assert "https://second.test/opds" in str(app.screen.query_one("#status-line").renderable)
        await pilot.press("enter")

        assert isinstance(app.screen, FeedScreen)
        assert workflow.fetch_urls == [None]
        assert app.screen.catalog == catalogs[1]


@pytest.mark.asyncio
async def test_catalog_screen_empty_state_uses_catalog_list_widget(tmp_path: Path) -> None:
    config = AppConfig(library_path=tmp_path, catalogs=[])
    app = ShelflineApp(config=config)

    async with app.run_test():
        catalog_list = app.screen.query_one("#catalog-list")
        rows = list(app.screen.query("#catalog-list .catalog-row"))
        rendered = str(catalog_list.renderable)
        detail = str(app.screen.query_one("#status-line").renderable)

    assert isinstance(catalog_list, CatalogList)
    assert rows == []
    assert "No catalogs configured" in rendered
    assert "Press a to add a catalog" in detail


@pytest.mark.asyncio
async def test_feed_screen_keeps_book_details_inline_on_enter() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(_feed()))
        await app.screen.open_entry(0)
        await pilot.pause()

        assert isinstance(app.screen, FeedScreen)
        assert "Interesting Book" in str(app.screen.query_one("#catalog-entry-detail").renderable)
        assert "d download" in str(app.screen.query_one("#catalog-entry-detail").renderable)


@pytest.mark.asyncio
async def test_feed_screen_open_entry_updates_inline_selection_and_detail() -> None:
    feed = CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated="2026-05-30",
        entries=[
            _entry(),
            CatalogEntry(
                title="Second Book",
                identifier="urn:book:second",
                updated="2026-05-31",
                authors=["Katherine Johnson"],
                acquisition_links=[
                    AcquisitionLink(
                        href="https://example.test/books/second.epub",
                        relation="http://opds-spec.org/acquisition",
                        media_type="application/epub+zip",
                        title="EPUB",
                    )
                ],
            ),
        ],
    )
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed))
        await pilot.pause()
        await app.screen.open_entry(1)
        await pilot.pause()

        detail_rendered = str(app.screen.query_one("#catalog-entry-detail").renderable)
        feed_body = app.screen.query_one("#feed-body", FeedEntryList)
        list_rendered = str(feed_body.renderable)

    assert "Second Book" in detail_rendered
    assert "Katherine Johnson" in detail_rendered
    assert feed_body.selected_index == 1
    assert "> 2." in list_rendered
    assert "Second Book" in list_rendered


@pytest.mark.asyncio
async def test_entry_screen_enables_terminal_graphics_in_auto_cover_mode() -> None:
    app = ShelflineApp(
        config=AppConfig(
            library_path=Path("books"),
            preferences=AppPreferences(covers=CoverPreferences(display="auto")),
        )
    )

    async with app.run_test():
        await app.push_screen(EntryScreen(_entry()))
        cover = app.screen.query_one("#cover-display", CoverDisplay)

        assert cover.display_mode == "auto"
        assert cover.terminal_graphics is True


@pytest.mark.asyncio
async def test_entry_screen_passes_cover_renderer_preference(tmp_path: Path) -> None:
    feed = _feed()
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[catalog],
        preferences={"covers": {"display": "auto", "renderer": "sixel"}},
    )
    app = ShelflineApp(config=config)

    async with app.run_test():
        await app.push_screen(FeedScreen(feed, catalog=catalog))
        cover = app.screen.query_one("#catalog-entry-detail").query_one(CoverDisplay)

    assert cover.renderer == "sixel"


@pytest.mark.asyncio
async def test_catalog_entry_screen_passes_cover_renderer_preference(tmp_path: Path) -> None:
    entry = _entry()
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[catalog],
        preferences={"covers": {"display": "auto", "renderer": "tgp"}},
    )
    app = ShelflineApp(config=config)

    async with app.run_test():
        await app.push_screen(EntryScreen(entry, catalog=catalog))
        cover = app.screen.query_one("#cover-display", CoverDisplay)

    assert cover.renderer == "tgp"


@pytest.mark.asyncio
async def test_library_detail_passes_cover_renderer_preference(tmp_path: Path) -> None:
    book_path = tmp_path / "book.epub"
    book_path.write_bytes(b"book")
    cover_path = tmp_path / "cover.jpg"
    cover_path.write_bytes(b"cover")
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(
        BookRecord(
            title="Library Book",
            authors=["Ada Lovelace"],
            identifiers=[],
            source_catalog="Example",
            source_entry_url="https://example.test/book",
            acquisition_url="https://example.test/book.epub",
            media_type="application/epub+zip",
            cover_image_url="https://example.test/cover.jpg",
            cover_image_path=cover_path,
            local_file_path=book_path,
        )
    )
    config = AppConfig(
        library_path=tmp_path,
        preferences={"covers": {"display": "auto", "renderer": "halfcell"}},
    )
    app = ShelflineApp(config=config, library=repo)

    async with app.run_test():
        await app.push_screen(LibraryScreen(library=repo))
        cover = app.screen.query_one("#cover-display", CoverDisplay)

    assert cover.renderer == "halfcell"


@pytest.mark.asyncio
async def test_feed_screen_enter_binding_keeps_book_details_inline() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(_feed()))
        await pilot.press("enter")

        assert isinstance(app.screen, FeedScreen)
        assert "Interesting Book" in str(app.screen.query_one("#catalog-entry-detail").renderable)


@pytest.mark.asyncio
async def test_feed_screen_selection_moves_before_opening_entry() -> None:
    feed = CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_navigation_entry(), _entry()],
    )
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed))
        await pilot.press("j")

        rendered = str(app.screen.query_one("#feed-body").renderable)
        assert "> 2." in rendered
        assert f"{BOOK_LABEL.text} Interesting Book" in rendered
        await pilot.press("enter")

        assert isinstance(app.screen, FeedScreen)
        assert "Interesting Book" in str(app.screen.query_one("#catalog-entry-detail").renderable)


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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.press("enter")
        assert isinstance(app.screen, FeedScreen)
        assert app.screen.feed.title == "Fiction Feed"

        await pilot.press("b")

        assert isinstance(app.screen, FeedScreen)
        assert app.screen.feed.title == "Root Feed"


@pytest.mark.asyncio
async def test_entry_screen_footer_shows_back_hint() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(EntryScreen(_entry()))
        footer = app.screen.query_one("#key-hints", KeyHintFooter)

        assert "b back" in EntryScreen.KEY_HINT
        assert "b back" in str(footer.render())


@pytest.mark.asyncio
async def test_entry_screen_back_binding_returns_to_feed_screen() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(_feed()))
        feed_screen = app.screen
        await app.push_screen(EntryScreen(_entry()))
        assert isinstance(app.screen, EntryScreen)

        await pilot.press("b")

        assert app.screen is feed_screen


@pytest.mark.asyncio
async def test_entry_screen_renders_cover_fallback_and_all_acquisitions() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(EntryScreen(_entry()))
        screen = app.screen
        rendered = str(screen.query_one("#entry-body").renderable)
        cover = str(screen.query_one("#cover-display").renderable)

        screen.begin_download("Preparing download")
        busy = str(screen.query_one("#busy-indicator").renderable)

    assert "Interesting Book" in rendered
    assert "A small but useful book." in rendered
    assert f"{DOWNLOADS_LABEL.text}:" in rendered
    assert f"> {glyph(DOWNLOADS_LABEL)} EPUB - application/epub+zip" in rendered
    assert "application/epub+zip" in rendered
    assert "application/pdf" in rendered
    assert "Ada Lovelace" in cover
    assert "Preparing download" in busy


@pytest.mark.asyncio
async def test_entry_screen_reports_available_cover_when_catalog_entry_has_cover_url() -> None:
    entry = CatalogEntry(
        title="Covered Book",
        identifier="urn:book:covered",
        updated="2026-05-30",
        authors=["Ada Lovelace"],
        cover_image_url="https://example.test/covers/covered.jpg",
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/covered.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(EntryScreen(entry))
        cover = str(app.screen.query_one("#cover-display").renderable)

    assert "Cover available" in cover
    assert "Cover unavailable" not in cover


@pytest.mark.asyncio
async def test_feed_screen_selected_book_cover_fetches_inline_detail_cover(
    tmp_path: Path,
) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    cover_path = tmp_path / "covers" / "covered.jpg"
    cover_path.parent.mkdir()
    cover_path.write_bytes(b"cover")
    workflow = FakeWorkflow()
    workflow.catalog_cover_path = cover_path
    entry = CatalogEntry(
        title="Covered Book",
        identifier="urn:book:covered",
        updated="2026-05-30",
        authors=["Ada Lovelace"],
        cover_image_url="https://example.test/covers/covered.jpg",
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/covered.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    feed = CatalogFeed(
        title="Covered Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[entry],
    )
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            catalogs=[catalog],
            preferences=AppPreferences(covers=CoverPreferences(display="auto")),
        ),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
        detail = app.screen.query_one("#catalog-entry-detail")
        cover = detail.query_one(CoverDisplay)

    assert workflow.catalog_cover_requests == [(catalog, entry)]
    assert cover.image_path == cover_path
    assert cover.cache_status == "cached"


@pytest.mark.asyncio
async def test_feed_screen_open_selected_keeps_cached_inline_cover(
    tmp_path: Path,
) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    cover_path = tmp_path / "covers" / "covered.jpg"
    cover_path.parent.mkdir()
    cover_path.write_bytes(b"cover")
    workflow = FakeWorkflow()
    workflow.catalog_cover_path = cover_path
    entry = CatalogEntry(
        title="Covered Book",
        identifier="urn:book:covered",
        updated="2026-05-30",
        authors=["Ada Lovelace"],
        cover_image_url="https://example.test/covers/covered.jpg",
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/covered.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    feed = CatalogFeed(
        title="Covered Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[entry],
    )
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            catalogs=[catalog],
            preferences=AppPreferences(covers=CoverPreferences(display="auto")),
        ),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

        cached_cover = app.screen.query_one("#catalog-entry-detail").query_one(CoverDisplay)
        assert cached_cover.image_path == cover_path
        assert cached_cover.cache_status == "cached"

        await pilot.press("enter")
        await pilot.pause()

        cover = app.screen.query_one("#catalog-entry-detail").query_one(CoverDisplay)

    assert workflow.catalog_cover_requests == [(catalog, entry)]
    assert cover.image_path == cover_path
    assert cover.cache_status == "cached"


@pytest.mark.asyncio
async def test_feed_screen_clears_stale_cover_when_selection_has_no_cover(
    tmp_path: Path,
) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    cover_path = tmp_path / "covers" / "covered.jpg"
    cover_path.parent.mkdir()
    cover_path.write_bytes(b"cover")
    workflow = FakeWorkflow()
    workflow.catalog_cover_path = cover_path
    first_entry = CatalogEntry(
        title="Covered Book",
        identifier="urn:book:covered",
        updated="2026-05-30",
        authors=["Ada Lovelace"],
        cover_image_url="https://example.test/covers/covered.jpg",
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/covered.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    second_entry = CatalogEntry(
        title="Plain Book",
        identifier="urn:book:plain",
        updated="2026-05-31",
        authors=["Mary Shelley"],
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/plain.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    feed = CatalogFeed(
        title="Covered Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[first_entry, second_entry],
    )
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            catalogs=[catalog],
            preferences=AppPreferences(covers=CoverPreferences(display="auto")),
        ),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

        cached_cover = app.screen.query_one("#catalog-entry-detail").query_one(CoverDisplay)
        assert cached_cover.image_path == cover_path
        assert cached_cover.cache_status == "cached"

        await pilot.press("j")
        await pilot.pause()

        detail = app.screen.query_one("#catalog-entry-detail")
        cover = detail.query_one(CoverDisplay)

    assert workflow.catalog_cover_requests == [(catalog, first_entry)]
    assert "Plain Book" in str(detail.renderable)
    assert cover.image_path is None
    assert cover.cache_status is None


@pytest.mark.asyncio
async def test_feed_screen_selected_book_cover_ignores_stale_fetch_result(
    tmp_path: Path,
) -> None:
    class SlowCoverWorkflow(FakeWorkflow):
        def __init__(self) -> None:
            super().__init__()
            self.cover_requested = asyncio.Event()
            self.release_cover = asyncio.Event()

        async def cache_catalog_entry_cover(
            self,
            catalog: CatalogConfig,
            entry: CatalogEntry,
        ) -> Path | None:
            self.catalog_cover_requests.append((catalog, entry))
            self.cover_requested.set()
            await self.release_cover.wait()
            return self.catalog_cover_path

    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    cover_path = tmp_path / "covers" / "covered.jpg"
    cover_path.parent.mkdir()
    cover_path.write_bytes(b"cover")
    workflow = SlowCoverWorkflow()
    workflow.catalog_cover_path = cover_path
    first_entry = CatalogEntry(
        title="Covered Book",
        identifier="urn:book:covered",
        updated="2026-05-30",
        authors=["Ada Lovelace"],
        cover_image_url="https://example.test/covers/covered.jpg",
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/covered.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    second_entry = CatalogEntry(
        title="Plain Book",
        identifier="urn:book:plain",
        updated="2026-05-31",
        authors=["Mary Shelley"],
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/plain.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    feed = CatalogFeed(
        title="Covered Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[first_entry, second_entry],
    )
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            catalogs=[catalog],
            preferences=AppPreferences(covers=CoverPreferences(display="auto")),
        ),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.pause()
        await asyncio.wait_for(workflow.cover_requested.wait(), timeout=1)

        await pilot.press("j")
        await pilot.pause()
        workflow.release_cover.set()
        await pilot.pause()

        detail = app.screen.query_one("#catalog-entry-detail")
        cover = detail.query_one(CoverDisplay)

    assert workflow.catalog_cover_requests == [(catalog, first_entry)]
    assert "Plain Book" in str(detail.renderable)
    assert cover.image_path is None
    assert cover.cache_status is None


@pytest.mark.asyncio
async def test_entry_screen_cleans_html_summary_for_detail_display() -> None:
    entry = CatalogEntry(
        title="Escaped Story",
        identifier="urn:book:escaped",
        updated="2026-05-31",
        authors=["Mary Shelley"],
        summary=(
            "&lt;p&gt;A &amp; B &lt;em&gt;story&lt;/em&gt;.&lt;/p&gt;"
            "&lt;p&gt;Line&lt;br /&gt;break&lt;/p&gt;"
        ),
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/escaped.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(EntryScreen(entry))
        detail = app.screen.query_one("#entry-body")
        rendered = str(detail.renderable)

    assert detail.has_class("entry-detail")
    assert "Escaped Story" in rendered
    assert "Mary Shelley" in rendered
    assert "A & B story." in rendered
    assert "Line\nbreak" in rendered
    assert "&lt;" not in rendered
    assert "&gt;" not in rendered
    assert "&amp;" not in rendered
    assert "<p>" not in rendered
    assert "</p>" not in rendered
    assert "<br" not in rendered


@pytest.mark.asyncio
async def test_entry_screen_uses_acquisition_rows_for_selection() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry()))

        rows = list(app.screen.query("#entry-body .acquisition-row"))
        assert [row.id for row in rows] == ["acquisition-0", "acquisition-1"]
        assert rows[0].has_class("selected")
        assert not rows[1].has_class("selected")
        assert str(rows[0].query_one(".row-marker").render()) == ">"
        assert "application/epub+zip" in str(rows[0].renderable)
        assert "https://example.test/books/interesting.epub" not in str(rows[0].renderable)

        await pilot.press("j")

        rows = list(app.screen.query("#entry-body .acquisition-row"))
        assert not rows[0].has_class("selected")
        assert rows[1].has_class("selected")
        assert str(rows[1].query_one(".row-marker").render()) == ">"


@pytest.mark.asyncio
async def test_entry_screen_downloads_acquisition_through_workflow(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(download_path=tmp_path / "Interesting Book.pdf")
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry(), catalog=catalog, workflow=workflow))
        await app.screen.download_acquisition(1)
        await pilot.pause()

        assert isinstance(app.screen, DownloadStatusScreen)
        assert workflow.downloads[0][2] == _entry().acquisition_links[1]
        assert "Download complete" in str(app.screen.query_one("#download-status").renderable)
        assert "Keys:" not in str(app.screen.query_one("#status-line").renderable)
        assert DownloadStatusScreen.KEY_HINT in str(
            app.screen.query_one("#key-hints", KeyHintFooter).render()
        )


@pytest.mark.asyncio
async def test_entry_screen_download_binding_uses_workflow(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(download_path=tmp_path / "Interesting Book.epub")
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry(), catalog=catalog, workflow=workflow))
        await pilot.press("d")

        assert isinstance(app.screen, DownloadStatusScreen)
        assert workflow.downloads[0][2] == _entry().acquisition_links[0]


@pytest.mark.asyncio
async def test_download_status_back_returns_to_entry_screen(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(download_path=tmp_path / "Interesting Book.epub")
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=AppConfig(library_path=tmp_path), workflow=workflow, library=repo)

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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EntryScreen(_entry(), catalog=catalog, workflow=workflow))
        await pilot.press("j")

        assert f"> {glyph(DOWNLOADS_LABEL)} PDF" in str(app.screen.query_one("#entry-body").renderable)
        await pilot.press("d")

        assert isinstance(app.screen, DownloadStatusScreen)
        assert workflow.downloads[0][2] == _entry().acquisition_links[1]


@pytest.mark.asyncio
async def test_download_status_screen_renders_known_and_unknown_progress() -> None:
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(LibraryScreen(library=repo))
        screen = app.screen
        assert "Interesting Book" in str(screen.query_one("#library-body").renderable)
        assert UNREAD_LABEL.text in str(screen.query_one("#library-body").renderable)

        screen.action_toggle_read()
        assert repo.list_books()[0].is_read is True
        assert READ_LABEL.text in str(screen.query_one("#library-body").renderable)

        screen.action_delete_book()
        assert repo.list_books() == []
        assert "No downloaded books" in str(screen.query_one("#library-body").renderable)


@pytest.mark.asyncio
async def test_library_screen_detail_pane_shows_selected_book_metadata_on_mount(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=False))
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(LibraryScreen(library=repo))

        rendered = _visible_library_detail_text(app.screen)
        assert "Dune" in rendered
        assert "Ada Lovelace" in rendered
        assert UNREAD_LABEL.text in rendered
        assert "application/epub+zip" in rendered
        assert "Example" in rendered
        assert f"{LOCAL_PATH_LABEL.text}: {tmp_path / 'books' / 'Dune.epub'}" in rendered
        assert f"{OPEN_PREVIEW_LABEL.text}: Enter preview" in rendered


@pytest.mark.asyncio
async def test_library_detail_uses_cover_preferences(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    cover_path = tmp_path / "covers" / "dune.jpg"
    book = _book(tmp_path, title="Dune", is_read=False)
    repo.add_book(
        BookRecord(
            title=book.title,
            authors=book.authors,
            identifiers=book.identifiers,
            source_catalog=book.source_catalog,
            source_entry_url=book.source_entry_url,
            acquisition_url=book.acquisition_url,
            media_type=book.media_type,
            cover_image_url="https://example.test/covers/dune.jpg",
            cover_image_path=cover_path,
            local_file_path=book.local_file_path,
            is_read=book.is_read,
            thumbnail_url="https://example.test/covers/dune-thumb.jpg",
            cover_cache_status="failed",
        )
    )
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            preferences=AppPreferences(covers=CoverPreferences(display="text")),
        ),
        library=repo,
    )

    async with app.run_test():
        await app.push_screen(LibraryScreen(library=repo))
        rendered = "\n".join(
            str(static.render())
            for static in app.screen.query("#detail-region Static")
            if static.display
        )

    assert "Dune" in rendered
    assert "Cover available" in rendered
    assert "Cover unavailable" not in rendered


@pytest.mark.asyncio
async def test_library_detail_reports_available_cover_when_record_has_remote_url(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book = _book(tmp_path, title="Dune", is_read=False)
    repo.add_book(
        BookRecord(
            title=book.title,
            authors=book.authors,
            identifiers=book.identifiers,
            source_catalog=book.source_catalog,
            source_entry_url=book.source_entry_url,
            acquisition_url=book.acquisition_url,
            media_type=book.media_type,
            cover_image_url="https://example.test/covers/dune.jpg",
            cover_image_path=None,
            local_file_path=book.local_file_path,
            is_read=book.is_read,
            thumbnail_url="https://example.test/covers/dune-thumb.jpg",
            cover_cache_status="missing",
        )
    )
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            preferences=AppPreferences(covers=CoverPreferences(display="text")),
        ),
        library=repo,
    )

    async with app.run_test():
        await app.push_screen(LibraryScreen(library=repo))
        rendered = "\n".join(
            str(static.render())
            for static in app.screen.query("#detail-region Static")
            if static.display
        )

    assert "Dune" in rendered
    assert "Cover available" in rendered
    assert "Cover unavailable" not in rendered


@pytest.mark.asyncio
async def test_library_screen_backfills_remote_cover_and_updates_selected_detail(
    tmp_path: Path,
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    cover_path = tmp_path / "covers" / "dune.jpg"
    cover_path.parent.mkdir()
    cover_path.write_bytes(b"cover")
    book = _book(tmp_path, title="Dune", is_read=False)
    old_record = BookRecord(
        title=book.title,
        authors=book.authors,
        identifiers=book.identifiers,
        source_catalog=book.source_catalog,
        source_entry_url=book.source_entry_url,
        acquisition_url=book.acquisition_url,
        media_type=book.media_type,
        cover_image_url="https://example.test/covers/dune.jpg",
        cover_image_path=None,
        local_file_path=book.local_file_path,
        is_read=book.is_read,
        thumbnail_url="https://example.test/covers/dune-thumb.jpg",
        cover_cache_status="missing",
    )
    repo.add_book(old_record)
    workflow = FakeWorkflow()
    workflow.library = repo
    workflow.book_cover_path = cover_path
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            preferences=AppPreferences(covers=CoverPreferences(display="auto")),
        ),
        workflow=workflow,
        library=repo,
    )

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo, workflow=workflow))
        await pilot.pause()
        await pilot.pause()
        cover = app.screen.query_one("#cover-display", CoverDisplay)

    stored = repo.list_books()[0]
    assert workflow.book_cover_requests == [old_record]
    assert stored.cover_image_path == cover_path
    assert stored.cover_cache_status == "cached"
    assert cover.image_path == cover_path
    assert cover.cache_status == "cached"


@pytest.mark.asyncio
async def test_library_detail_enables_terminal_graphics_in_auto_cover_mode(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book = _book(tmp_path, title="Dune", is_read=False)
    repo.add_book(
        BookRecord(
            title=book.title,
            authors=book.authors,
            identifiers=book.identifiers,
            source_catalog=book.source_catalog,
            source_entry_url=book.source_entry_url,
            acquisition_url=book.acquisition_url,
            media_type=book.media_type,
            cover_image_url="https://example.test/covers/dune.jpg",
            cover_image_path=tmp_path / "covers" / "dune.jpg",
            local_file_path=book.local_file_path,
            is_read=book.is_read,
            cover_cache_status="cached",
        )
    )
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            preferences=AppPreferences(covers=CoverPreferences(display="auto")),
        ),
        library=repo,
    )

    async with app.run_test():
        await app.push_screen(LibraryScreen(library=repo))
        cover = app.screen.query_one("#cover-display", CoverDisplay)

        assert cover.display_mode == "auto"
        assert cover.terminal_graphics is True


@pytest.mark.asyncio
async def test_library_screen_detail_pane_updates_when_selection_moves(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=False))
    repo.add_book(_book(tmp_path, title="Foundation", is_read=True))
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        rendered = _visible_library_detail_text(app.screen)
        assert "Dune" in rendered
        assert "Read status:" in rendered
        assert UNREAD_LABEL.text in rendered
        assert "Foundation" not in rendered

        await pilot.press("j")

        rendered = _visible_library_detail_text(app.screen)
        assert "Foundation" in rendered
        assert "Read status:" in rendered
        assert READ_LABEL.text in rendered
        assert "Status: Selected Foundation" in rendered
        assert "Dune" not in rendered


@pytest.mark.asyncio
async def test_library_screen_detail_pane_updates_when_read_status_toggles(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=False))
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.pause()

        screen = app.screen
        rendered = _visible_library_detail_text(screen)
        assert "Dune" in rendered
        assert "Read status:" in rendered
        assert UNREAD_LABEL.text in rendered

        screen.action_toggle_read()
        await pilot.pause()

        rendered = _visible_library_detail_text(screen)
        assert "Dune" in rendered
        assert "Read status:" in rendered
        assert READ_LABEL.text in rendered
        assert "Status: Read status updated" in rendered


@pytest.mark.asyncio
async def test_library_screen_detail_pane_updates_when_selected_book_is_deleted(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=False))
    repo.add_book(_book(tmp_path, title="Foundation", is_read=True))
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.pause()
        screen = app.screen

        screen.action_delete_book()
        await pilot.pause()

        rendered = _visible_library_detail_text(screen)
        assert "Foundation" in rendered
        assert "Read status:" in rendered
        assert READ_LABEL.text in rendered
        assert "Status: Book deleted" in rendered
        assert "Dune" not in rendered

        screen.action_delete_book()
        await pilot.pause()

        rendered = _visible_library_detail_text(screen)
        assert "No downloaded books" in rendered
        assert "Status: Book deleted" in rendered
        assert "Foundation" not in rendered


@pytest.mark.asyncio
async def test_library_screen_detail_pane_shows_empty_message_for_empty_library(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(LibraryScreen(library=repo))

        rendered = _visible_library_detail_text(app.screen)
        assert "No downloaded books" in rendered
        assert "Catalogs" in rendered


@pytest.mark.asyncio
async def test_library_screen_uses_book_row_widgets_for_selection(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=False))
    repo.add_book(_book(tmp_path, title="Foundation", is_read=True))
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))

        rows = list(app.screen.query("#library-body .library-book-row"))
        assert [row.id for row in rows] == ["library-book-0", "library-book-1"]
        assert rows[0].has_class("state-unread")
        assert rows[1].has_class("state-read")
        assert rows[0].has_class("selected")
        assert not rows[1].has_class("selected")
        assert "Ada Lovelace" in str(rows[0].renderable)
        assert "Unread" in str(rows[0].renderable)
        assert "Read" in str(rows[1].renderable)
        assert "application/epub+zip" in str(rows[0].renderable)
        assert f"{LOCAL_PATH_LABEL.text}: {tmp_path}" in str(rows[0].renderable)

        await pilot.press("j")

        rows = list(app.screen.query("#library-body .library-book-row"))
        assert not rows[0].has_class("selected")
        assert rows[1].has_class("selected")


@pytest.mark.asyncio
async def test_library_screen_many_books_use_contiguous_scrollable_rows(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    for index in range(24):
        repo.add_book(_book(tmp_path, title=f"Library Book {index + 1:02d}", is_read=False))
    app = ShelflineApp(config=None)

    async with app.run_test(size=(80, 24)) as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.pause()

        library_body = app.screen.query_one("#library-body")
        rows = list(app.screen.query("#library-body .library-book-row"))

        assert isinstance(library_body, LibraryBookList)
        assert isinstance(library_body, VerticalScroll)
        assert [row.id for row in rows[:6]] == [
            "library-book-0",
            "library-book-1",
            "library-book-2",
            "library-book-3",
            "library-book-4",
            "library-book-5",
        ]
        assert [str(row.query_one(".row-index").render()) for row in rows[:6]] == [
            "1.",
            "2.",
            "3.",
            "4.",
            "5.",
            "6.",
        ]
        assert all(row.styles.margin.top == 0 for row in rows)
        assert all(row.region.height > 0 for row in rows[:3])
        assert library_body.max_scroll_y > 0

        await pilot.press(*(["j"] * 18))
        await pilot.pause()

        rows = list(app.screen.query("#library-body .library-book-row"))
        selected_row = rows[18]
        assert selected_row.has_class("selected")
        assert str(selected_row.query_one(".row-marker").render()) == ">"
        assert selected_row.region.height > 0
        assert library_body.scroll_y > 0
        assert library_body.region.y <= selected_row.region.y
        assert selected_row.region.y + selected_row.region.height <= library_body.region.y + library_body.region.height


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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.press("j")

        assert "> 2. Second Book" in str(app.screen.query_one("#library-body").renderable)
        assert app.screen.selected_book is not None
        assert app.screen.selected_book.title == "Second Book"

        await pilot.press("enter")

        assert isinstance(app.screen, EpubReaderScreen)


@pytest.mark.asyncio
async def test_library_screen_open_reader_applies_reader_preferences(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, is_read=False))
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            preferences=AppPreferences(
                reader=ReaderPreferences(
                    width="wide",
                    theme="warm",
                    paragraph_spacing="relaxed",
                    show_progress=False,
                    show_chapter_title=False,
                )
            ),
        ),
        library=repo,
    )

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.press("enter")

        assert isinstance(app.screen, EpubReaderScreen)
        page = app.screen.query_one("#reader-page")
        progress = app.screen.query_one("#reader-progress")
        heading = app.screen.query_one("#reader-heading")

        assert page.has_class("reader-width-wide")
        assert page.has_class("reader-theme-warm")
        assert page.has_class("reader-spacing-relaxed")
        assert progress.display is False
        assert heading.display is False


@pytest.mark.asyncio
async def test_library_screen_reports_epub_preview_failure_without_opening_reader(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    stale_book = _book(tmp_path, is_read=False)
    stale_book.local_file_path.unlink()
    repo.add_book(stale_book)
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        assert "No downloaded books" in str(app.screen.query_one("#library-body").renderable)
        assert "No downloaded books" in _visible_library_detail_text(app.screen)

        repo.add_book(_book(tmp_path, is_read=False))
        await pilot.press("r")

        assert "Interesting Book" in str(app.screen.query_one("#library-body").renderable)
        assert "Library refreshed" in str(app.screen.query_one("#status-line").renderable)
        detail = _visible_library_detail_text(app.screen)
        assert "Interesting Book" in detail
        assert "Status: Library refreshed" in detail


@pytest.mark.asyncio
async def test_library_screen_filters_books_by_search_text(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=False))
    repo.add_book(_book(tmp_path, title="Foundation", is_read=True))
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.press("/")
        app.screen.query_one("#library-search").value = "dune"
        await pilot.press("enter")

        rendered = str(app.screen.query_one("#library-body").renderable)
        assert "Dune" in rendered
        assert "Foundation" not in rendered
        assert "Search: dune" in str(app.screen.query_one("#status-line").renderable)
        detail = _visible_library_detail_text(app.screen)
        assert "Dune" in detail
        assert "Foundation" not in detail
        assert "Status: Search: dune" in detail

        await pilot.press("/")
        app.screen.query_one("#library-search").value = "missing"
        await pilot.press("enter")

        rendered = str(app.screen.query_one("#library-body").renderable)
        assert "No downloaded books" in rendered
        assert "Dune" not in rendered
        assert "Foundation" not in rendered
        detail = _visible_library_detail_text(app.screen)
        assert "No downloaded books" in detail
        assert "Status: Search: missing" in detail
        assert "Dune" not in detail
        assert "Foundation" not in detail


@pytest.mark.asyncio
async def test_library_screen_preserves_search_during_library_actions(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, title="Dune", is_read=False))
    repo.add_book(_book(tmp_path, title="Dune Messiah", is_read=False))
    repo.add_book(_book(tmp_path, title="Foundation", is_read=False))
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

    def assert_menu_only_in_footer() -> None:
        assert "Keys:" in str(app.screen.query_one("#key-hints", KeyHintFooter).render())
        assert list(app.screen.query(Footer)) == []
        if app.screen.query("#status-line"):
            assert "Keys:" not in str(app.screen.query_one("#status-line").renderable)

    async with app.run_test():
        assert isinstance(app.screen, SetupScreen)
        assert_menu_only_in_footer()

        await app.push_screen(CatalogsScreen(AppConfig(library_path=tmp_path)))
        assert_menu_only_in_footer()

        await app.push_screen(FeedScreen(_feed()))
        assert_menu_only_in_footer()

        await app.push_screen(EntryScreen(_entry()))
        assert_menu_only_in_footer()

        await app.push_screen(DownloadStatusScreen())
        assert_menu_only_in_footer()

        await app.push_screen(LibraryScreen(library=repo))
        assert_menu_only_in_footer()

        preview = EpubPreview(
            title="Preview Title",
            outline=(EpubOutlineItem(title="Chapter One", section_index=0),),
            sections=(EpubSection(heading="Chapter One", text="Plain text body."),),
        )
        await app.push_screen(EpubPreviewScreen(preview))
        assert_menu_only_in_footer()

        await app.push_screen(
            CatalogAuthScreen(CatalogConfig(name="Private", url="https://example.test/opds"))
        )
        assert_menu_only_in_footer()


@pytest.mark.asyncio
async def test_app_library_bindings_delegate_to_active_library_screen(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, is_read=False))
    config = AppConfig(library_path=tmp_path)
    app = ShelflineApp(config=config, library=repo)

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
    app = ShelflineApp(config=config, library=repo)

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
    app = ShelflineApp(config=config, library=repo)

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
    app = ShelflineApp(config=config)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, CatalogsScreen)
        assert screen.query_one("#catalog-form").display is False

        screen.action_toggle_add_catalog()

        assert screen.query_one("#catalog-form").display is True


@pytest.mark.asyncio
async def test_catalog_screen_add_binding_toggles_form_without_pushing_screen(
    tmp_path: Path,
) -> None:
    config = AppConfig(library_path=tmp_path, catalogs=[])
    app = ShelflineApp(config=config)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, CatalogsScreen)
        assert screen.query_one("#catalog-form").display is False

        await pilot.press("a")
        await pilot.pause()

        assert app.screen is screen
        assert screen.query_one("#catalog-form").display is True

        await pilot.press("a")
        await pilot.pause()

        assert app.screen is screen
        assert screen.query_one("#catalog-form").display is False


@pytest.mark.asyncio
async def test_catalog_screen_add_form_has_visible_cancel_button(tmp_path: Path) -> None:
    config = AppConfig(library_path=tmp_path, catalogs=[])
    app = ShelflineApp(config=config)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, CatalogsScreen)

        screen.action_toggle_add_catalog()

        button = screen.query_one("#cancel-add-catalog")
        assert button.parent is screen.query_one("#catalog-form")


@pytest.mark.asyncio
async def test_catalog_screen_cancel_add_form_hides_form_without_pushing_screen(
    tmp_path: Path,
) -> None:
    config = AppConfig(library_path=tmp_path, catalogs=[])
    app = ShelflineApp(config=config)

    async with app.run_test() as pilot:
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, CatalogsScreen)
        screen.action_toggle_add_catalog()
        await pilot.pause()
        assert screen.query_one("#catalog-form").display is True

        await pilot.click("#cancel-add-catalog")
        await pilot.pause()

        assert app.screen is screen
        assert screen.query_one("#catalog-form").display is False
        assert "Add catalog form hidden" in str(screen.query_one("#status-line").renderable)


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
    app = ShelflineApp(
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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(CatalogAuthScreen(catalog))
        screen = app.screen
        rendered = str(screen.query_one("#auth-body").renderable)

    assert "Private Catalog" in rendered
    assert "reader" in rendered
    assert "secret-password" not in rendered
    assert screen.credentials == {"username": "reader", "password": "secret-password"}
