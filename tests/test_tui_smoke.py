from __future__ import annotations

import json
from pathlib import Path

import pytest

from epub_tui.app import EpubTuiApp
from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.downloads import DownloadProgress
from epub_tui.library import BookRecord, LibraryRepository
from epub_tui.tui.screens import CatalogsScreen, LibraryScreen, SetupScreen
from epub_tui.tui.widgets import CatalogList, CatalogRow, CoverDisplay, DownloadProgressDisplay


@pytest.mark.asyncio
async def test_app_opens_setup_screen_without_config() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test():
        assert isinstance(app.screen, SetupScreen)
        assert "Library path" in str(app.screen.query_one("#setup-title").renderable)


@pytest.mark.asyncio
async def test_app_opens_catalog_screen_with_config_and_no_catalogs(tmp_path: Path) -> None:
    config = AppConfig(library_path=tmp_path, catalogs=[])
    app = EpubTuiApp(config=config)

    async with app.run_test():
        assert isinstance(app.screen, CatalogsScreen)


@pytest.mark.asyncio
async def test_app_opens_catalog_screen_with_config_catalogs_and_empty_library(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[CatalogConfig(name="Standard Ebooks", url="https://standardebooks.org/opds")],
    )
    app = EpubTuiApp(config=config, library=repo)

    async with app.run_test():
        assert isinstance(app.screen, CatalogsScreen)


@pytest.mark.asyncio
async def test_app_opens_library_screen_with_config_catalogs_and_books(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(
        BookRecord(
            title="Interesting Book",
            authors=["Ada Lovelace"],
            identifiers=["urn:book:interesting"],
            source_catalog="Standard Ebooks",
            source_entry_url="https://standardebooks.org/opds/book",
            acquisition_url="https://standardebooks.org/books/interesting.epub",
            media_type="application/epub+zip",
            cover_image_url=None,
            cover_image_path=None,
            local_file_path=tmp_path / "Interesting Book.epub",
        )
    )
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[CatalogConfig(name="Standard Ebooks", url="https://standardebooks.org/opds")],
    )
    app = EpubTuiApp(config=config, library=repo)

    async with app.run_test():
        assert isinstance(app.screen, LibraryScreen)


@pytest.mark.asyncio
async def test_app_opens_catalog_screen_when_library_check_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()

    def fail_list_books() -> list[BookRecord]:
        raise OSError("database unavailable")

    monkeypatch.setattr(repo, "list_books", fail_list_books)
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[CatalogConfig(name="Standard Ebooks", url="https://standardebooks.org/opds")],
    )
    app = EpubTuiApp(config=config, library=repo)

    async with app.run_test():
        assert isinstance(app.screen, CatalogsScreen)


@pytest.mark.asyncio
async def test_catalog_screen_renders_saved_catalogs(tmp_path: Path) -> None:
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[
            CatalogConfig(name="Standard Ebooks", url="https://standardebooks.org/opds"),
            CatalogConfig(
                name="Feedbooks",
                url="https://example.com/opds",
                auth={"username": "reader", "password": "secret"},
            ),
        ],
    )
    app = EpubTuiApp(config=config)

    async with app.run_test():
        catalog_list = app.screen.query_one("#catalog-list")
        rows = list(app.screen.query("#catalog-list .catalog-row"))
        text = catalog_list.renderable

    assert isinstance(catalog_list, CatalogList)
    assert all(isinstance(row, CatalogRow) for row in rows)
    assert [row.id for row in rows] == ["catalog-row-0", "catalog-row-1"]
    assert rows[0].has_class("selected")
    assert not rows[1].has_class("selected")
    assert "Standard Ebooks" in str(text)
    assert "Feedbooks" in str(text)
    assert "https://standardebooks.org/opds" in str(text)
    assert "— No auth" in str(text)
    assert "🔒 Basic auth" in str(text)


@pytest.mark.asyncio
async def test_catalog_screen_uses_bottom_action_area(tmp_path: Path) -> None:
    config = AppConfig(library_path=tmp_path, catalogs=[])
    app = EpubTuiApp(config=config)

    async with app.run_test():
        action_area = app.screen.query_one("#catalog-actions")
        button = app.screen.query_one("#show-add-catalog")
        assert button.parent is action_area
        assert action_area.parent.id == "main-region"


@pytest.mark.asyncio
async def test_catalog_screen_adds_catalog_to_config_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config = AppConfig(library_path=tmp_path / "books", catalogs=[])
    app = EpubTuiApp(config=config, config_path=config_path)

    async with app.run_test():
        screen = app.screen
        assert isinstance(screen, CatalogsScreen)
        screen.query_one("#catalog-name").value = "Example"
        screen.query_one("#catalog-url").value = "https://example.test/opds"

        screen.add_catalog_from_inputs()

        assert app.config is not None
        assert app.config.catalogs[0].name == "Example"
        assert "Example" in str(screen.query_one("#catalog-list").renderable)

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["catalogs"] == [{"name": "Example", "url": "https://example.test/opds"}]


def test_setup_screen_validates_library_path(tmp_path: Path) -> None:
    screen = SetupScreen()

    assert screen.validate_library_path(tmp_path) is None
    assert screen.validate_library_path(tmp_path / "missing") == "Library path must exist"


def test_setup_screen_rejects_blank_library_path() -> None:
    screen = SetupScreen()

    assert screen.validate_library_path("") == "Library path is required"
    assert screen.validate_library_path("   ") == "Library path is required"


@pytest.mark.asyncio
async def test_setup_screen_saves_library_path_and_opens_catalogs(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    library_path = tmp_path / "books"
    library_path.mkdir()
    app = EpubTuiApp(config=None, config_path=config_path)

    async with app.run_test() as pilot:
        screen = app.screen
        assert isinstance(screen, SetupScreen)
        screen.query_one("#library-path").value = str(library_path)

        await screen.complete_setup()
        await pilot.pause()

        assert isinstance(app.screen, CatalogsScreen)
        assert app.config is not None
        assert app.config.library_path == library_path
        assert app.workflow is not None
        assert app.library is app.workflow.library

    saved = json.loads(config_path.read_text(encoding="utf-8"))
    assert saved["library_path"] == str(library_path)


@pytest.mark.asyncio
async def test_catalog_screen_busy_indicator_for_outgoing_call(tmp_path: Path) -> None:
    config = AppConfig(library_path=tmp_path)
    app = EpubTuiApp(config=config)

    async with app.run_test():
        screen = app.screen
        assert isinstance(screen, CatalogsScreen)

        screen.begin_outgoing_call("Loading catalog")
        assert "Loading catalog" in str(screen.query_one("#busy-indicator").renderable)
        assert "Loading catalog" in str(screen.query_one("#status-line").renderable)

        screen.finish_outgoing_call()
        assert "Ready" in str(screen.query_one("#status-line").renderable)
        assert str(screen.query_one("#busy-indicator").renderable) == ""


def test_download_progress_display_known_total() -> None:
    display = DownloadProgressDisplay()

    display.update_progress(DownloadProgress(bytes_received=25, total_bytes=100))

    assert "25%" in str(display.renderable)


def test_download_progress_display_unknown_total() -> None:
    display = DownloadProgressDisplay()

    display.update_progress(DownloadProgress(bytes_received=2048, total_bytes=None))

    rendered = str(display.renderable)
    assert "2048 bytes" in rendered
    assert "indeterminate" in rendered


def test_cover_display_falls_back_without_terminal_graphics() -> None:
    display = CoverDisplay(title="Example Book", authors=["Ada Lovelace"], image_path=None)

    rendered = str(display.renderable)

    assert "Example Book" in rendered
    assert "Ada Lovelace" in rendered


def test_cover_display_falls_back_when_terminal_graphics_requested(tmp_path: Path) -> None:
    image_path = tmp_path / "cover.jpg"
    image_path.write_bytes(b"not a real image")

    display = CoverDisplay(
        title="Example Book",
        authors=["Ada Lovelace"],
        image_path=image_path,
        terminal_graphics=True,
    )

    rendered = str(display.renderable)

    assert "Example Book" in rendered
    assert "Ada Lovelace" in rendered
    assert str(image_path) not in rendered
