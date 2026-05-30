from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from epub_tui.app import EpubTuiApp
from epub_tui.config import ConfigError, default_config_path, load_config


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

    config_path = args.config or default_config or default_config_path()
    if not config_path.exists():
        return EpubTuiApp(config=None)

    try:
        config = load_config(config_path)
    except ConfigError as exc:
        raise SystemExit(f"Config error: {exc}") from exc

    return EpubTuiApp(config=config)


def main(argv: Sequence[str] | None = None) -> None:
    build_app(argv).run()


if __name__ == "__main__":
    main()
