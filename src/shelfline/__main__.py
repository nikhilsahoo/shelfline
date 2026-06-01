from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from shelfline.app import ShelflineApp
from shelfline.config import ConfigError, default_config_path, load_config
from shelfline.credentials import CredentialStore
from shelfline.services import CatalogWorkflow


def build_app(
    argv: Sequence[str] | None = None,
    default_config: Path | None = None,
) -> ShelflineApp:
    parser = argparse.ArgumentParser(
        prog="shelfline",
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
            return ShelflineApp(config=None, config_path=config_path)
        if not config_path.is_file():
            raise ConfigError(f"Config path is not a file: {config_path}")
        config = load_config(config_path)
    except (ConfigError, OSError) as exc:
        raise SystemExit(f"Config error: {exc}") from exc

    workflow = CatalogWorkflow(
        config=config,
        state_db=_default_state_db(config.library_path),
        credentials=CredentialStore(),
    )
    return ShelflineApp(config=config, workflow=workflow, config_path=config_path)


def main(argv: Sequence[str] | None = None) -> None:
    build_app(argv).run()


def _default_state_db(library_path: Path) -> Path:
    return library_path / ".shelfline" / "state.db"


if __name__ == "__main__":
    main()
