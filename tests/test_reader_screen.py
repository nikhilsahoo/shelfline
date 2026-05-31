from __future__ import annotations

from pathlib import Path

import pytest
from ebooklib import epub
from textual.containers import VerticalScroll

from epub_tui.app import EpubTuiApp
from epub_tui.library import BookRecord, LibraryRepository
from epub_tui.reader import EpubOutlineItem, EpubPreview, EpubSection
from epub_tui.tui.reader import EpubReaderScreen
from epub_tui.tui.screens import LibraryScreen


def _preview() -> EpubPreview:
    return EpubPreview(
        title="Reader Title",
        outline=(
            EpubOutlineItem(title="Chapter One", section_index=0),
            EpubOutlineItem(title="Chapter Two", section_index=1),
        ),
        sections=(
            EpubSection(heading="Chapter One", text="First section body."),
            EpubSection(heading="Chapter Two", text="Second section body."),
        ),
    )


def _write_reader_epub(epub_path: Path, title: str = "Reader Book") -> None:
    book = epub.EpubBook()
    book.set_identifier(title)
    book.set_title(title)
    book.set_language("en")
    first = epub.EpubHtml(title="Chapter One", file_name="chapter-one.xhtml", lang="en")
    first.content = b"<html><body><h1>Chapter One</h1><p>First section body.</p></body></html>"
    second = epub.EpubHtml(title="Chapter Two", file_name="chapter-two.xhtml", lang="en")
    second.content = b"<html><body><h1>Chapter Two</h1><p>Second section body.</p></body></html>"
    book.add_item(first)
    book.add_item(second)
    book.spine = ["nav", first, second]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)


def _book(tmp_path: Path) -> BookRecord:
    book_path = tmp_path / "books" / "reader-book.epub"
    book_path.parent.mkdir(exist_ok=True)
    _write_reader_epub(book_path)
    return BookRecord(
        title="Reader Book",
        authors=["Ada Lovelace"],
        identifiers=["urn:book:reader"],
        source_catalog="Example",
        source_entry_url="https://example.test/opds/book",
        acquisition_url="https://example.test/books/reader-book.epub",
        media_type="application/epub+zip",
        cover_image_url=None,
        cover_image_path=None,
        local_file_path=book_path,
        is_read=False,
    )


@pytest.mark.asyncio
async def test_reader_screen_renders_current_section_and_progress() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(EpubReaderScreen(_preview()))

        assert "Reader Title" in str(app.screen.query_one("#reader-title").renderable)
        assert "Chapter One" in str(app.screen.query_one("#reader-heading").renderable)
        assert "First section body." in str(
            app.screen.query_one("#reader-body-text").render()
        )
        assert "1 / 2" in str(app.screen.query_one("#reader-progress").renderable)
        assert "Keys:" in str(app.screen.query_one("#status-line").renderable)


@pytest.mark.asyncio
async def test_reader_screen_body_is_scrollable() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(EpubReaderScreen(_preview()))

        assert isinstance(app.screen.query_one("#reader-body"), VerticalScroll)
        assert "First section body." in str(
            app.screen.query_one("#reader-body-text").render()
        )


@pytest.mark.asyncio
async def test_reader_screen_next_and_previous_update_section_and_progress() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview()))

        await pilot.press("n")

        assert "Chapter Two" in str(app.screen.query_one("#reader-heading").renderable)
        assert "Second section body." in str(
            app.screen.query_one("#reader-body-text").render()
        )
        assert "2 / 2" in str(app.screen.query_one("#reader-progress").renderable)

        await pilot.press("p")

        assert "Chapter One" in str(app.screen.query_one("#reader-heading").renderable)
        assert "First section body." in str(
            app.screen.query_one("#reader-body-text").render()
        )
        assert "1 / 2" in str(app.screen.query_one("#reader-progress").renderable)


@pytest.mark.asyncio
async def test_library_screen_enter_on_epub_opens_reader_screen(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path))
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.press("enter")

        assert isinstance(app.screen, EpubReaderScreen)
        assert "Reader Book" in str(app.screen.query_one("#reader-title").renderable)
