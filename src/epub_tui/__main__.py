from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from epub_tui.app import EpubTuiApp
from epub_tui.config import ConfigError, default_config_path, load_config
from epub_tui.services import CatalogWorkflow


def build_app(
    argv: Sequence[str] | None = None,
    default_config: Path | None = None,
) -> EpubTuiApp:
    parser = argparse.ArgumentParser(
        prog="epub-tui",
        description="Browse OPDS catalogs and manage downloaded EPUBs in the terminal.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to a JSON config file.",
    )
    args = parser.parse_args(argv)

    explicit_config = args.config is not None
    config_path = args.config or default_config or default_config_path()
    try:
        if not config_path.exists():
            if explicit_config:
                raise ConfigError(f"Config file does not exist: {config_path}")
            return EpubTuiApp(config=None, config_path=config_path)
        if not config_path.is_file():
            raise ConfigError(f"Config path is not a file: {config_path}")
        config = load_config(config_path)
    except (ConfigError, OSError) as exc:
        raise SystemExit(f"Config error: {exc}") from exc

    workflow = CatalogWorkflow(config=config, state_db=_default_state_db(config.library_path))
    return EpubTuiApp(config=config, workflow=workflow, config_path=config_path)


def main(argv: Sequence[str] | None = None) -> None:
    build_app(argv).run()


def _default_state_db(library_path: Path) -> Path:
    return library_path / ".epub-tui" / "state.db"


if __name__ == "__main__":
    main()
