from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static


class EpubTuiApp(App[None]):
    TITLE = "epub-tui"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("l", "show_library", "Library"),
        ("m", "toggle_read", "Read/Unread"),
        ("x", "delete_book", "Delete Book"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("epub-tui catalog-first MVP")
        yield Footer()

    def action_show_library(self) -> None:
        self.notify("Library screen is not wired yet")

    def action_toggle_read(self) -> None:
        self.notify("Read/unread is available from the library screen")

    def action_delete_book(self) -> None:
        self.notify("Delete is available from the library screen")
