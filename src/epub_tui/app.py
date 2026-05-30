from textual.app import App

from epub_tui.config import AppConfig
from epub_tui.tui.screens import CatalogsScreen, SetupScreen


class EpubTuiApp(App[None]):
    TITLE = "epub-tui"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("l", "show_library", "Library"),
        ("m", "toggle_read", "Read/Unread"),
        ("x", "delete_book", "Delete Book"),
    ]

    def __init__(self, config: AppConfig | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.config = config

    def on_mount(self) -> None:
        if self.config is None:
            self.push_screen(SetupScreen())
            return

        self.push_screen(CatalogsScreen(self.config))

    def action_show_library(self) -> None:
        self.notify("Library screen is not wired yet")

    def action_toggle_read(self) -> None:
        self.notify("Read/unread is available from the library screen")

    def action_delete_book(self) -> None:
        self.notify("Delete is available from the library screen")
