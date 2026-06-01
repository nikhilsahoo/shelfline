from textual.app import App

from pathlib import Path

from shelfline.config import AppConfig, CatalogConfig, save_config
from shelfline.credentials import CredentialStore
from shelfline.library import LibraryRepository
from shelfline.services import CatalogWorkflow
from shelfline.tui.screens import CatalogsScreen, LibraryScreen, SetupScreen


class ShelflineApp(App[None]):
    TITLE = "Shelfline"
    CSS_PATH = "tui/app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("c", "show_catalogs", "Catalogs"),
        ("a", "add_catalog", "Add Catalog"),
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
        self.push_screen(self._initial_screen())

    def _initial_screen(self) -> SetupScreen | CatalogsScreen | LibraryScreen:
        if self.config is None:
            return SetupScreen()

        if self.config.catalogs and self._library_has_books():
            return LibraryScreen(library=self.library)

        return CatalogsScreen(self.config, workflow=self.workflow)

    def _library_has_books(self) -> bool:
        if self.library is None:
            return False

        try:
            return bool(self.library.list_books())
        except Exception:
            return False

    def apply_config(self, config: AppConfig) -> None:
        self.config = config
        self.workflow = CatalogWorkflow(
            config=config,
            state_db=self._state_db_path(config.library_path),
            credentials=CredentialStore(),
        )
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
        return library_path / ".shelfline" / "state.db"

    def action_show_library(self) -> None:
        if self.library is not None:
            self.push_screen(LibraryScreen(library=self.library))
            return

        self.notify("Library screen is not wired yet")

    def action_show_catalogs(self) -> None:
        self._push_catalogs()

    def action_add_catalog(self) -> None:
        self._push_catalogs(show_add_form=True)

    def _push_catalogs(self, *, show_add_form: bool = False) -> None:
        if self.config is None:
            self.notify("Catalogs are available after setup")
            return

        self.push_screen(
            CatalogsScreen(
                self.config,
                workflow=self.workflow,
                show_add_form=show_add_form,
            )
        )

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
