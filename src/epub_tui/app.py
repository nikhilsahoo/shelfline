from textual.app import App

from epub_tui.config import AppConfig
from epub_tui.library import LibraryRepository
from epub_tui.services import CatalogWorkflow
from epub_tui.tui.screens import CatalogsScreen, LibraryScreen, SetupScreen


class EpubTuiApp(App[None]):
    TITLE = "epub-tui"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("l", "show_library", "Library"),
        ("m", "toggle_read", "Read/Unread"),
        ("x", "delete_book", "Delete Book"),
    ]

    def __init__(
        self,
        config: AppConfig | None = None,
        *,
        workflow: CatalogWorkflow | None = None,
        library: LibraryRepository | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.config = config
        self.workflow = workflow
        self.library = library or getattr(workflow, "library", None)

    def on_mount(self) -> None:
        if self.config is None:
            self.push_screen(SetupScreen())
            return

        self.push_screen(CatalogsScreen(self.config, workflow=self.workflow))

    def action_show_library(self) -> None:
        if self.library is not None:
            self.push_screen(LibraryScreen(library=self.library))
            return

        self.notify("Library screen is not wired yet")

    def action_toggle_read(self) -> None:
        if isinstance(self.screen, LibraryScreen):
            self.screen.action_toggle_read()
            return

        self.notify("Read/unread is available from the library screen")

    def action_delete_book(self) -> None:
        if isinstance(self.screen, LibraryScreen):
            self.screen.action_delete_book()
            return

        self.notify("Delete is available from the library screen")
