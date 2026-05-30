from __future__ import annotations

from pathlib import Path

import pytest

from epub_tui.app import EpubTuiApp
from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.downloads import DownloadProgress
from epub_tui.tui.screens import CatalogsScreen, SetupScreen
from epub_tui.tui.widgets import CoverDisplay, DownloadProgressDisplay


@pytest.mark.asyncio
async def test_app_opens_setup_screen_without_config() -> None:
    app = EpubTuiApp(config=None)

    async with app.run_test():
        assert isinstance(app.screen, SetupScreen)


@pytest.mark.asyncio
async def test_app_opens_catalog_screen_with_config(tmp_path: Path) -> None:
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[CatalogConfig(name="Standard Ebooks", url="https://standardebooks.org/opds")],
    )
    app = EpubTuiApp(config=config)

    async with app.run_test():
        assert isinstance(app.screen, CatalogsScreen)


@pytest.mark.asyncio
async def test_catalog_screen_renders_saved_catalogs(tmp_path: Path) -> None:
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[
            CatalogConfig(name="Standard Ebooks", url="https://standardebooks.org/opds"),
            CatalogConfig(name="Feedbooks", url="https://example.com/opds"),
        ],
    )
    app = EpubTuiApp(config=config)

    async with app.run_test():
        text = app.screen.query_one("#catalog-list").renderable

    assert "Standard Ebooks" in str(text)
    assert "Feedbooks" in str(text)


def test_setup_screen_validates_library_path(tmp_path: Path) -> None:
    screen = SetupScreen()

    assert screen.validate_library_path(tmp_path) is None
    assert screen.validate_library_path(tmp_path / "missing") == "Library path must exist"


def test_setup_screen_rejects_blank_library_path() -> None:
    screen = SetupScreen()

    assert screen.validate_library_path("") == "Library path is required"
    assert screen.validate_library_path("   ") == "Library path is required"


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
