from pathlib import Path

import pytest

from epub_tui.__main__ import build_app
from epub_tui.app import EpubTuiApp


def test_build_app_returns_textual_app(tmp_path: Path) -> None:
    app = build_app([], default_config=tmp_path / "missing.json")
    assert isinstance(app, EpubTuiApp)


def test_build_app_uses_default_config_when_present(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    library_path = tmp_path / "books"
    config_path.write_text(
        (
            "{\n"
            f'  "library_path": "{library_path.as_posix()}",\n'
            '  "catalogs": [{"name": "Example", "url": "https://example.test/opds"}],\n'
            '  "preferences": {}\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    app = build_app([], default_config=config_path)

    assert app.config is not None
    assert app.config.catalogs[0].name == "Example"


def test_build_app_uses_explicit_config_over_default(tmp_path: Path) -> None:
    default_config = tmp_path / "default.json"
    explicit_config = tmp_path / "explicit.json"
    default_config.write_text(
        (
            "{\n"
            f'  "library_path": "{(tmp_path / "default-books").as_posix()}",\n'
            '  "catalogs": [{"name": "Default", "url": "https://default.test/opds"}],\n'
            '  "preferences": {}\n'
            "}\n"
        ),
        encoding="utf-8",
    )
    explicit_config.write_text(
        (
            "{\n"
            f'  "library_path": "{(tmp_path / "explicit-books").as_posix()}",\n'
            '  "catalogs": [{"name": "Explicit", "url": "https://explicit.test/opds"}],\n'
            '  "preferences": {}\n'
            "}\n"
        ),
        encoding="utf-8",
    )

    app = build_app(["--config", str(explicit_config)], default_config=default_config)

    assert app.config is not None
    assert app.config.catalogs[0].name == "Explicit"


def test_build_app_exits_for_invalid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text("[]\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        build_app(["--config", str(config_path)])

    assert "Config root must be a JSON object" in str(exc_info.value)


def test_build_app_exits_for_missing_explicit_config(tmp_path: Path) -> None:
    config_path = tmp_path / "missing.json"

    with pytest.raises(SystemExit) as exc_info:
        build_app(["--config", str(config_path)])

    assert f"Config file does not exist: {config_path}" in str(exc_info.value)


def test_build_app_exits_for_directory_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config-dir"
    config_path.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        build_app(["--config", str(config_path)])

    assert f"Config path is not a file: {config_path}" in str(exc_info.value)
