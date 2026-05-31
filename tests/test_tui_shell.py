from __future__ import annotations

from pathlib import Path

import pytest

from epub_tui.app import EpubTuiApp
from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.library import LibraryRepository
from epub_tui.tui.layout import KeyHintFooter, ShellHeader
from epub_tui.tui.screens import CatalogsScreen, LibraryScreen


@pytest.mark.asyncio
async def test_catalog_screen_uses_shell_regions(tmp_path: Path) -> None:
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[CatalogConfig(name="Example", url="https://example.test/opds")],
    )
    app = EpubTuiApp(config=config)

    async with app.run_test():
        screen = app.screen

        assert isinstance(screen, CatalogsScreen)
        assert screen.query_one("#shell-header", ShellHeader)
        assert screen.query_one("#key-hints", KeyHintFooter)
        assert screen.query_one("#main-region")
        assert screen.query_one("#detail-region")


@pytest.mark.asyncio
async def test_library_screen_uses_shell_regions(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    app = EpubTuiApp(config=AppConfig(library_path=tmp_path), library=repo)

    async with app.run_test() as pilot:
        app.action_show_library()
        await pilot.pause()

        assert isinstance(app.screen, LibraryScreen)
        assert app.screen.query_one("#shell-header", ShellHeader)
        assert app.screen.query_one("#key-hints", KeyHintFooter)
        assert app.screen.query_one("#main-region")
        assert app.screen.query_one("#detail-region")
