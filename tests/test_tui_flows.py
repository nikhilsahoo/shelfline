from __future__ import annotations

from pathlib import Path

import pytest

from epub_tui.app import EpubTuiApp
from epub_tui.catalog.models import AcquisitionLink, CatalogEntry, CatalogFeed
from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.downloads import DownloadProgress
from epub_tui.library import BookRecord, LibraryRepository
from epub_tui.reader import EpubOutlineItem, EpubPreview, EpubSection
from epub_tui.tui.screens import (
    CatalogAuthScreen,
    DownloadStatusScreen,
    EntryScreen,
    EpubPreviewScreen,
    FeedScreen,
    LibraryScreen,
)


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


def _book(tmp_path: Path, *, is_read: bool = False) -> BookRecord:
    book_path = tmp_path / "books" / "interesting.epub"
    book_path.parent.mkdir(exist_ok=True)
    book_path.write_bytes(b"book")
    return BookRecord(
        title="Interesting Book",
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
        entries=[_entry()],
    )
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(FeedScreen(feed))
        screen = app.screen

        rendered = str(screen.query_one("#feed-body").renderable)
        assert "Example Feed" in rendered
        assert "Interesting Book" in rendered

        screen.begin_fetch("Fetching feed")
        assert "Fetching feed" in str(screen.query_one("#busy-indicator").renderable)
        screen.begin_refresh("Refreshing feed")
        assert "Refreshing feed" in str(screen.query_one("#busy-indicator").renderable)
        screen.begin_navigation("Opening next page")
        assert "Opening next page" in str(screen.query_one("#busy-indicator").renderable)


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
