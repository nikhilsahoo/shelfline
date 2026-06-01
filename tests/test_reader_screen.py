from __future__ import annotations

import json
from pathlib import Path

import pytest
from ebooklib import epub
from textual.containers import VerticalScroll
from textual.pilot import Pilot
from textual.widgets import Footer

from shelfline.app import ShelflineApp
from shelfline.config import AppConfig, ReaderPreferences
from shelfline.library import Bookmark, BookRecord, LibraryRepository, ReadingProgress
from shelfline.reader import EpubOutlineItem, EpubPreview, EpubSection
from shelfline.tui.layout import KeyHintFooter
from shelfline.tui.reader import EpubReaderScreen
from shelfline.tui.screens import LibraryScreen


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


def _long_outline_preview(section_count: int = 40) -> EpubPreview:
    sections = tuple(
        EpubSection(
            heading=f"Chapter {index + 1}",
            text=f"Section {index + 1} body.",
        )
        for index in range(section_count)
    )
    return EpubPreview(
        title="Reader Title",
        outline=tuple(
            EpubOutlineItem(title=section.heading, section_index=index)
            for index, section in enumerate(sections)
        ),
        sections=sections,
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
        bookmark_list_error: RuntimeError | None = None,
    ) -> None:
        self.load_error = load_error
        self.save_error = save_error
        self.bookmark_list_error = bookmark_list_error

    def get_reading_progress(self, book_path: Path) -> ReadingProgress | None:
        if self.load_error is not None:
            raise self.load_error
        return None

    def save_reading_progress(self, progress: ReadingProgress) -> None:
        if self.save_error is not None:
            raise self.save_error

    def list_bookmarks(self, book_path: Path) -> tuple[Bookmark, ...]:
        if self.bookmark_list_error is not None:
            raise self.bookmark_list_error
        return ()

    def add_bookmark(self, bookmark: object) -> object:
        raise RuntimeError("bookmark database unavailable")


@pytest.mark.asyncio
async def test_reader_screen_renders_current_section_and_progress() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(EpubReaderScreen(_preview()))

        assert "Reader Title" in str(app.screen.query_one("#reader-title").renderable)
        assert "Chapter One" in str(app.screen.query_one("#reader-heading").renderable)
        assert "First section body." in str(
            app.screen.query_one("#reader-body-text").render()
        )
        assert "1 / 2" in str(app.screen.query_one("#reader-progress").renderable)
        assert "Keys:" not in str(app.screen.query_one("#status-line").renderable)
        assert EpubReaderScreen.KEY_HINT in str(
            app.screen.query_one("#key-hints", KeyHintFooter).render()
        )


@pytest.mark.asyncio
async def test_reader_screen_uses_custom_key_hint_footer() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(EpubReaderScreen(_preview()))

        footer = app.screen.query_one("#key-hints", KeyHintFooter)
        assert EpubReaderScreen.KEY_HINT in str(footer.render())
        assert list(app.screen.query(Footer)) == []


@pytest.mark.asyncio
async def test_reader_screen_key_hint_includes_table_of_contents() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(EpubReaderScreen(_preview()))

        assert "t toc" in str(app.screen.query_one("#key-hints", KeyHintFooter).render())


@pytest.mark.asyncio
async def test_reader_screen_key_hint_includes_zen_mode() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(EpubReaderScreen(_preview()))

        assert "z zen" in str(app.screen.query_one("#key-hints", KeyHintFooter).render())


@pytest.mark.asyncio
async def test_reader_screen_t_opens_table_of_contents_with_outline_items() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview()))

        await pilot.press("t")

        assert app.screen.__class__.__name__ == "ReaderTocScreen"
        assert "Chapter One" in str(app.screen.query_one("#toc-list").render())
        assert "Chapter Two" in str(app.screen.query_one("#toc-list").render())
        assert list(app.screen.query(Footer)) == []


@pytest.mark.asyncio
async def test_reader_toc_j_and_k_change_selection() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview()))
        await pilot.press("t")

        toc = app.screen
        assert toc.__class__.__name__ == "ReaderTocScreen"
        assert toc.selected_index == 0

        await pilot.press("j")
        assert toc.selected_index == 1

        await pilot.press("k")
        assert toc.selected_index == 0


@pytest.mark.asyncio
async def test_reader_toc_scrolls_to_keep_long_outline_selection_visible() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test(size=(80, 12)) as pilot:
        await app.push_screen(EpubReaderScreen(_long_outline_preview()))
        await pilot.press("t")

        toc_list = app.screen.query_one("#toc-list", VerticalScroll)
        assert toc_list.scroll_y == 0

        for _ in range(25):
            await pilot.press("j")

        assert app.screen.selected_index == 25
        assert toc_list.scroll_y > 0
        selected_row = app.screen.query_one("#toc-row-25")
        assert toc_list.region.y <= selected_row.region.y < toc_list.region.bottom


@pytest.mark.asyncio
async def test_reader_toc_enter_jumps_to_selected_section_and_saves_progress(
    tmp_path: Path,
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "reader-book.epub"
    app = ShelflineApp(config=None)

    async with app.run_test(size=(80, 20)) as pilot:
        await app.push_screen(
            EpubReaderScreen(_long_preview(), library=repo, book_path=book_path)
        )
        reader = app.screen
        assert isinstance(reader, EpubReaderScreen)
        reader_body = reader.query_one("#reader-body", VerticalScroll)
        await _scroll_reader_body(reader_body, y=20, pilot=pilot)

        await pilot.press("t")
        await pilot.press("j")
        await pilot.press("enter")

        assert app.screen is reader
        assert reader.section_index == 1
        assert "Chapter Two" in str(reader.query_one("#reader-heading").renderable)
        assert "Second section line 0" in str(reader.query_one("#reader-body-text").render())
        assert "2 / 2" in str(reader.query_one("#reader-progress").renderable)
        assert reader_body.scroll_y == 0
        progress = repo.get_reading_progress(book_path)
        assert progress is not None
        assert progress.section_index == 1
        assert progress.position == 0


@pytest.mark.asyncio
async def test_reader_toc_b_dismisses_without_changing_reader_section() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview()))
        reader = app.screen
        assert isinstance(reader, EpubReaderScreen)

        await pilot.press("t")
        await pilot.press("j")
        await pilot.press("b")

        assert app.screen is reader
        assert reader.section_index == 0
        assert "Chapter One" in str(reader.query_one("#reader-heading").renderable)


@pytest.mark.asyncio
async def test_reader_toc_falls_back_to_section_headings_when_outline_is_empty() -> None:
    preview = EpubPreview(title="Reader Title", outline=(), sections=_preview().sections)
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(preview))

        await pilot.press("t")

        assert app.screen.__class__.__name__ == "ReaderTocScreen"
        assert "Chapter One" in str(app.screen.query_one("#toc-list").render())
        assert "Chapter Two" in str(app.screen.query_one("#toc-list").render())


@pytest.mark.asyncio
async def test_reader_bookmark_navigator_opens_and_jumps(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "reader-book.epub"
    repo.add_bookmark(Bookmark(book_path, section_index=1, label="Chapter Two"))
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(
            EpubReaderScreen(_preview(), library=repo, book_path=book_path)
        )

        await pilot.press("g")

        assert app.screen.__class__.__name__ == "ReaderBookmarkScreen"
        assert "Chapter Two" in str(app.screen.query_one("#bookmark-list").render())

        await pilot.press("enter")

        assert isinstance(app.screen, EpubReaderScreen)
        assert app.screen.section_index == 1


@pytest.mark.asyncio
async def test_reader_bookmark_navigator_reports_load_failure(tmp_path: Path) -> None:
    library = _FailingProgressLibrary(
        bookmark_list_error=RuntimeError("bookmark database unavailable")
    )
    book_path = tmp_path / "books" / "reader-book.epub"
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(
            EpubReaderScreen(_preview(), library=library, book_path=book_path)
        )
        reader = app.screen
        assert isinstance(reader, EpubReaderScreen)

        await pilot.press("g")

        assert app.screen.__class__.__name__ == "ReaderBookmarkScreen"
        assert "Bookmarks unavailable: bookmark database unavailable" in str(
            app.screen.query_one("#bookmark-title").renderable
        )
        assert "No bookmarks" in str(app.screen.query_one("#bookmark-list").render())
        assert "Bookmarks unavailable: bookmark database unavailable" in str(
            reader.query_one("#status-line").renderable
        )


@pytest.mark.asyncio
async def test_reader_screen_body_is_scrollable() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(EpubReaderScreen(_preview()))

        assert isinstance(app.screen.query_one("#reader-body"), VerticalScroll)
        assert "First section body." in str(
            app.screen.query_one("#reader-body-text").render()
        )


@pytest.mark.asyncio
async def test_reader_screen_uses_constrained_reading_surface() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(EpubReaderScreen(_preview()))

        surface = app.screen.query_one("#reader-surface")
        page = app.screen.query_one("#reader-page")
        chrome = app.screen.query_one("#reader-chrome")
        text = app.screen.query_one("#reader-body-text")

        assert surface.has_class("reader-surface")
        assert page.has_class("reader-page")
        assert chrome.has_class("reader-chrome")
        assert text.has_class("reader-text")
        assert "Reader Title" in str(chrome.renderable)
        assert "1 / 2" in str(chrome.renderable)


@pytest.mark.asyncio
async def test_reader_screen_applies_reader_preference_classes() -> None:
    app = ShelflineApp(config=None)
    preferences = ReaderPreferences(
        width="wide",
        theme="warm",
        paragraph_spacing="relaxed",
        show_progress=False,
        show_chapter_title=False,
    )

    async with app.run_test():
        await app.push_screen(EpubReaderScreen(_preview(), preferences=preferences))

        page = app.screen.query_one("#reader-page")
        progress = app.screen.query_one("#reader-progress")
        heading = app.screen.query_one("#reader-heading")

        assert page.has_class("reader-width-wide")
        assert page.has_class("reader-theme-warm")
        assert page.has_class("reader-spacing-relaxed")
        assert progress.display is False
        assert heading.display is False


@pytest.mark.asyncio
async def test_reader_preferences_overlay_changes_width_and_saves(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.json"
    config = AppConfig(library_path=tmp_path)
    app = ShelflineApp(config=config, config_path=config_path)

    async with app.run_test() as pilot:
        await app.push_screen(
            EpubReaderScreen(_preview(), preferences=config.preferences.reader)
        )
        reader = app.screen
        assert isinstance(reader, EpubReaderScreen)

        await pilot.press("o")
        await pilot.press("w")

        assert app.screen is reader
        assert reader.preferences.width == "wide"
        assert reader.query_one("#reader-page").has_class("reader-width-wide")

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["preferences"]["reader"]["width"] == "wide"


@pytest.mark.asyncio
async def test_reader_screen_body_reserves_gutter_before_scrollbar() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test(size=(100, 30)) as pilot:
        await app.push_screen(EpubReaderScreen(_long_preview()))
        await pilot.pause()

        reader_body = app.screen.query_one("#reader-body", VerticalScroll)
        reader_text = app.screen.query_one("#reader-body-text")
        scrollbar = reader_body.vertical_scrollbar

        assert scrollbar.region.x - reader_text.region.right >= 3


@pytest.mark.asyncio
async def test_reader_screen_next_and_previous_update_section_and_progress() -> None:
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

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
async def test_reader_zen_mode_hides_nonessential_chrome_and_preserves_scroll() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test(size=(80, 20)) as pilot:
        await app.push_screen(EpubReaderScreen(_long_preview()))
        reader = app.screen
        assert isinstance(reader, EpubReaderScreen)
        reader_body = reader.query_one("#reader-body", VerticalScroll)
        await _scroll_reader_body(reader_body, y=20, pilot=pilot)
        scroll_y = reader_body.scroll_y

        await pilot.press("z")
        await pilot.pause()

        assert reader.has_class("zen-mode")
        assert reader.query_one("#key-hints").display is False
        assert reader.query_one("#status-line").display is False
        assert reader_body.scroll_y == scroll_y

        await pilot.press("z")
        await pilot.pause()

        assert not reader.has_class("zen-mode")
        assert reader.query_one("#key-hints").display is True


@pytest.mark.asyncio
async def test_reader_zen_mode_surfaces_status_messages_temporarily() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test(size=(80, 20)) as pilot:
        await app.push_screen(EpubReaderScreen(_long_preview()))
        reader = app.screen
        assert isinstance(reader, EpubReaderScreen)

        await pilot.press("z")
        await pilot.pause()
        assert reader.query_one("#key-hints").display is False
        assert reader.query_one("#status-line").display is False

        await pilot.press("m")
        await pilot.pause()

        assert reader.query_one("#key-hints").display is False
        status_line = reader.query_one("#status-line")
        assert status_line.display is True
        assert "Bookmark requires library-backed book" in str(status_line.renderable)

        await pilot.press("z")
        await pilot.press("z")
        await pilot.pause()

        assert reader.has_class("zen-mode")
        assert reader.query_one("#key-hints").display is False
        assert reader.query_one("#status-line").display is False


@pytest.mark.asyncio
async def test_reader_screen_previous_at_first_section_preserves_body_scroll() -> None:
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

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
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview()))

        await pilot.press("n")

        assert app.screen.section_index == 1
        assert "Chapter Two" in str(app.screen.query_one("#reader-heading").renderable)
        assert "2 / 2" in str(app.screen.query_one("#reader-progress").renderable)


@pytest.mark.asyncio
async def test_reader_screen_adds_bookmark_with_current_section_heading(
    tmp_path: Path,
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "reader-book.epub"
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(
            EpubReaderScreen(
                _preview(),
                section_index=1,
                library=repo,
                book_path=book_path,
            )
        )

        await pilot.press("m")

        bookmarks = repo.list_bookmarks(book_path)
        assert len(bookmarks) == 1
        assert bookmarks[0].section_index == 1
        assert bookmarks[0].position == 0
        assert bookmarks[0].label == "Chapter Two"
        assert "Bookmark added" in str(app.screen.query_one("#status-line").renderable)


@pytest.mark.asyncio
async def test_reader_screen_toggles_bookmark_at_current_position(
    tmp_path: Path,
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "reader-book.epub"
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(
            EpubReaderScreen(
                _preview(),
                section_index=1,
                library=repo,
                book_path=book_path,
            )
        )

        await pilot.press("m")
        assert len(repo.list_bookmarks(book_path)) == 1
        assert "Bookmark added" in str(app.screen.query_one("#status-line").renderable)

        await pilot.press("m")

        assert repo.list_bookmarks(book_path) == []
        assert "Bookmark removed" in str(
            app.screen.query_one("#status-line").renderable
        )


@pytest.mark.asyncio
async def test_reader_screen_removes_duplicate_bookmarks_at_current_position(
    tmp_path: Path,
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "reader-book.epub"
    repo.add_bookmark(
        Bookmark(book_path, section_index=1, position=0, label="Duplicate A")
    )
    repo.add_bookmark(
        Bookmark(book_path, section_index=1, position=0, label="Duplicate B")
    )
    other = repo.add_bookmark(
        Bookmark(book_path, section_index=0, position=0, label="Other section")
    )
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(
            EpubReaderScreen(
                _preview(),
                section_index=1,
                library=repo,
                book_path=book_path,
            )
        )

        await pilot.press("m")

        assert [bookmark.id for bookmark in repo.list_bookmarks(book_path)] == [
            other.id
        ]
        assert "Bookmark removed" in str(
            app.screen.query_one("#status-line").renderable
        )


@pytest.mark.asyncio
async def test_reader_screen_reports_bookmark_requires_library_backed_book() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview()))

        await pilot.press("m")

        assert "Bookmark requires library-backed book" in str(
            app.screen.query_one("#status-line").renderable
        )


@pytest.mark.asyncio
async def test_library_screen_enter_on_epub_opens_reader_screen(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book = _book(tmp_path)
    repo.add_book(book)
    repo.save_reading_progress(ReadingProgress(book.local_file_path, section_index=1, position=0))
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(LibraryScreen(library=repo))
        await pilot.press("enter")

        assert isinstance(app.screen, EpubReaderScreen)
        assert app.screen.library is repo
        assert app.screen.book_path == book.local_file_path
        assert "Reader Book" in str(app.screen.query_one("#reader-title").renderable)
        assert "Chapter Two" in str(app.screen.query_one("#reader-heading").renderable)
