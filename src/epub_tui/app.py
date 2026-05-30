from textual.app import App

from pathlib import Path

from epub_tui.config import AppConfig, CatalogConfig, save_config
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
        config_path: Path | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self.config = config
        self.config_path = config_path
        self.workflow = workflow
        self.library = library or getattr(workflow, "library", None)

    def on_mount(self) -> None:
        if self.config is None:
            self.push_screen(SetupScreen())
            return

        self.push_screen(CatalogsScreen(self.config, workflow=self.workflow))

    def apply_config(self, config: AppConfig) -> None:
        self.config = config
        self.workflow = CatalogWorkflow(config=config, state_db=self._state_db_path(config.library_path))
        self.library = self.workflow.library
        if self.config_path is not None:
            save_config(self.config_path, config)

    async def complete_setup(self, library_path: Path) -> None:
        self.apply_config(AppConfig(library_path=library_path, catalogs=[], preferences={}))
        await self.push_screen(CatalogsScreen(self.config, workflow=self.workflow))

    def add_catalog(self, catalog: CatalogConfig) -> None:
        if self.config is None:
            return
        catalogs = [*self.config.catalogs, catalog]
        self.apply_config(
            AppConfig(
                library_path=self.config.library_path,
                catalogs=catalogs,
                preferences=dict(self.config.preferences),
            )
        )

    @staticmethod
    def _state_db_path(library_path: Path) -> Path:
        return library_path / ".epub-tui" / "state.db"

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
