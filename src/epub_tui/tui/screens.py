from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from epub_tui.config import AppConfig
from epub_tui.tui.widgets import BusyIndicator, StatusLine


class SetupScreen(Screen[None]):
    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Setup", id="setup-title")
        yield StatusLine("Ready", id="status-line")
        yield Footer()

    def validate_library_path(self, path: str | Path) -> str | None:
        if isinstance(path, str) and not path.strip():
            return "Library path is required"

        library_path = Path(path).expanduser()
        if not library_path.exists():
            return "Library path must exist"
        if not library_path.is_dir():
            return "Library path must be a directory"
        return None


class CatalogsScreen(Screen[None]):
    def __init__(self, config: AppConfig, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        yield StatusLine(self._catalog_text(), id="catalog-list")
        yield BusyIndicator(id="busy-indicator")
        yield StatusLine("Ready", id="status-line")
        yield Footer()

    def begin_outgoing_call(self, message: str) -> None:
        self.query_one("#busy-indicator", BusyIndicator).start(message)
        self.query_one("#status-line", StatusLine).set_message(message)

    def finish_outgoing_call(self, message: str = "Ready") -> None:
        self.query_one("#busy-indicator", BusyIndicator).stop()
        self.query_one("#status-line", StatusLine).set_message(message)

    def _catalog_text(self) -> str:
        if not self.config.catalogs:
            return "No catalogs configured"
        return "\n".join(catalog.name for catalog in self.config.catalogs)
