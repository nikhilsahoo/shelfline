from __future__ import annotations

from pathlib import Path

import pytest
from ebooklib import epub
from textual.containers import VerticalScroll
from textual.pilot import Pilot

from epub_tui.app import EpubTuiApp
from epub_tui.library import BookRecord, LibraryRepository, ReadingProgress
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


def _long_preview() -> EpubPreview:
    return EpubPreview(
        title="Reader Title",
        outline=(
            EpubOutlineItem(title="Chapter One", section_index=0),
            EpubOutlineItem(title="Chapter Two", section_index=1),
        ),
        sections=(
            EpubSection(
                heading="Chapter One",
                text="\n".join(f"First section line {index}" for index in range(80)),
            ),
            EpubSection(
                heading="Chapter Two",
                text="\n".join(f"Second section line {index}" for index in range(80)),
            ),
        ),
    )


async def _scroll_reader_body(reader_body: VerticalScroll, *, y: int, pilot: Pilot) -> None:
    for _ in range(10):
        reader_body.scroll_to(y=y, animate=False)
        await pilot.pause()
        if reader_body.scroll_y > 0:
            return

    pytest.fail(f"reader body did not scroll after requesting y={y}")


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


class _FailingProgressLibrary:
    def __init__(
        self,
        *,
        load_error: RuntimeError | None = None,
        save_error: RuntimeError | None = None,
    ) -> None:
        self.load_error = load_error
        self.save_error = save_error

    def get_reading_progress(self, book_path: Path) -> ReadingProgress | None:
        if self.load_error is not None:
            raise self.load_error
        return None

    def save_reading_progress(self, progress: ReadingProgress) -> None:
        if self.save_error is not None:
            raise self.save_error


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
async def test_reader_screen_next_resets_body_scroll_to_top() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test(size=(80, 20)) as pilot:
        await app.push_screen(EpubReaderScreen(_long_preview()))
        reader_body = app.screen.query_one("#reader-body", VerticalScroll)
        await _scroll_reader_body(reader_body, y=20, pilot=pilot)

        assert reader_body.scroll_y > 0

        await pilot.press("n")
        await pilot.pause()

        assert reader_body.scroll_y == 0


@pytest.mark.asyncio
async def test_reader_screen_next_at_last_section_preserves_body_scroll() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test(size=(80, 20)) as pilot:
        await app.push_screen(EpubReaderScreen(_long_preview(), section_index=1))
        reader_body = app.screen.query_one("#reader-body", VerticalScroll)
        await _scroll_reader_body(reader_body, y=20, pilot=pilot)

        assert reader_body.scroll_y > 0

        await pilot.press("n")
        await pilot.pause()

        assert reader_body.scroll_y > 0
        assert "2 / 2" in str(app.screen.query_one("#reader-progress").renderable)


@pytest.mark.asyncio
async def test_reader_screen_previous_at_first_section_preserves_body_scroll() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test(size=(80, 20)) as pilot:
        await app.push_screen(EpubReaderScreen(_long_preview()))
        reader_body = app.screen.query_one("#reader-body", VerticalScroll)
        await _scroll_reader_body(reader_body, y=20, pilot=pilot)

        assert reader_body.scroll_y > 0

        await pilot.press("p")
        await pilot.pause()

        assert reader_body.scroll_y > 0
        assert "1 / 2" in str(app.screen.query_one("#reader-progress").renderable)


@pytest.mark.asyncio
async def test_reader_screen_resumes_saved_progress_and_clamps_section(
    tmp_path: Path,
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "reader-book.epub"
    repo.save_reading_progress(ReadingProgress(book_path, section_index=99, position=12))
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(
            EpubReaderScreen(_preview(), library=repo, book_path=book_path)
        )

        assert app.screen.section_index == 1
        assert "Chapter Two" in str(app.screen.query_one("#reader-heading").renderable)
        assert "Second section body." in str(
            app.screen.query_one("#reader-body-text").render()
        )
        assert "2 / 2" in str(app.screen.query_one("#reader-progress").renderable)


@pytest.mark.asyncio
async def test_reader_screen_opens_when_progress_load_fails() -> None:
    library = _FailingProgressLibrary(load_error=RuntimeError("database locked"))
    app = EpubTuiApp(config=None)

    async with app.run_test():
        await app.push_screen(
            EpubReaderScreen(
                _preview(),
                library=library,  # type: ignore[arg-type]
                book_path=Path("reader-book.epub"),
            )
        )

        assert app.screen.section_index == 0
        assert "Chapter One" in str(app.screen.query_one("#reader-heading").renderable)
        assert "Progress unavailable: database locked" in str(
            app.screen.query_one("#status-line").renderable
        )


@pytest.mark.asyncio
async def test_reader_screen_saves_progress_on_section_changes(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "reader-book.epub"
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(
            EpubReaderScreen(_preview(), library=repo, book_path=book_path)
        )

        await pilot.press("n")

        progress = repo.get_reading_progress(book_path)
        assert progress is not None
        assert progress.section_index == 1
        assert progress.position == 0

        await pilot.press("p")

        progress = repo.get_reading_progress(book_path)
        assert progress is not None
        assert progress.section_index == 0
        assert progress.position == 0


@pytest.mark.asyncio
async def test_reader_screen_navigation_continues_when_progress_save_fails() -> None:
    library = _FailingProgressLibrary(save_error=RuntimeError("read-only database"))
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(
            EpubReaderScreen(
                _preview(),
                library=library,  # type: ignore[arg-type]
                book_path=Path("reader-book.epub"),
            )
        )

        await pilot.press("n")

        assert app.screen.section_index == 1
        assert "Chapter Two" in str(app.screen.query_one("#reader-heading").renderable)
        assert "2 / 2" in str(app.screen.query_one("#reader-progress").renderable)
        assert "Progress not saved: read-only database" in str(
            app.screen.query_one("#status-line").renderable
        )


@pytest.mark.asyncio
async def test_reader_screen_works_without_persistence_inputs() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview()))

        await pilot.press("n")

        assert app.screen.section_index == 1
        assert "Chapter Two" in str(app.screen.query_one("#reader-heading").renderable)
        assert "2 / 2" in str(app.screen.query_one("#reader-progress").renderable)


@pytest.mark.asyncio
async def test_library_screen_enter_on_epub_opens_reader_screen(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book = _book(tmp_path)
    repo.add_book(book)
    repo.save_reading_progress(ReadingProgress(book.local_file_path, section_index=1, position=0))
    app = EpubTuiApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.press("enter")

        assert isinstance(app.screen, EpubReaderScreen)
        assert app.screen.library is repo
        assert app.screen.book_path == book.local_file_path
        assert "Reader Book" in str(app.screen.query_one("#reader-title").renderable)
        assert "Chapter Two" in str(app.screen.query_one("#reader-heading").renderable)
