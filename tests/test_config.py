import json
import os
from pathlib import Path

import pytest

from epub_tui.config import (
    AppConfig,
    CatalogConfig,
    ConfigError,
    default_config_path,
    load_config,
    redact_config,
    save_config,
)


def test_load_config_with_catalog_and_basic_auth(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    library_path = tmp_path / "library"
    config_path.write_text(
        json.dumps(
            {
                "library_path": str(library_path),
                "catalogs": [
                    {
                        "name": "Private",
                        "url": "https://example.test/opds",
                        "auth": {"username": "alice", "password": "secret"},
                    }
                ],
                "preferences": {"theme": "textual-dark"},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.library_path == library_path
    assert config.catalogs[0].name == "Private"
    assert config.catalogs[0].auth == {"username": "alice", "password": "secret"}
    assert config.preferences == {"theme": "textual-dark"}


def test_save_config_is_human_editable_json(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[CatalogConfig(name="Public", url="https://example.test/opds")],
        preferences={},
    )

    save_config(config_path, config)

    text = config_path.read_text(encoding="utf-8")
    assert "\n  " in text
    loaded = json.loads(text)
    assert loaded["catalogs"][0]["name"] == "Public"


def test_save_config_restricts_file_permissions_when_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chmod_calls: list[tuple[Path, int]] = []

    def fake_chmod(path: Path, mode: int) -> None:
        chmod_calls.append((path, mode))

    monkeypatch.setattr("epub_tui.config.os.name", "posix")
    monkeypatch.setattr("epub_tui.config.os.chmod", fake_chmod)

    config_path = tmp_path / "config.json"
    config = AppConfig(library_path=tmp_path / "books")

    save_config(config_path, config)

    assert chmod_calls == [(config_path, 0o600)]


def test_save_config_writes_user_only_permissions_on_posix(tmp_path: Path) -> None:
    if os.name != "posix" or not hasattr(os, "umask"):
        pytest.skip("POSIX permission bits are not meaningful on this platform")

    config_path = tmp_path / "config.json"
    config = AppConfig(library_path=tmp_path / "books")

    old_umask = os.umask(0)
    try:
        save_config(config_path, config)
    finally:
        os.umask(old_umask)

    assert config_path.stat().st_mode & 0o777 == 0o600


def test_rejects_duplicate_catalog_names(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "library_path": str(tmp_path / "library"),
                "catalogs": [
                    {"name": "Same", "url": "https://one.test/opds"},
                    {"name": "Same", "url": "https://two.test/opds"},
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Duplicate catalog name: Same"):
        load_config(config_path)


def test_rejects_incomplete_basic_auth(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "library_path": str(tmp_path / "library"),
                "catalogs": [
                    {
                        "name": "Broken",
                        "url": "https://example.test/opds",
                        "auth": {"username": "alice"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="requires both username and password"):
        load_config(config_path)


def test_redact_config_hides_password(tmp_path: Path) -> None:
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[
            CatalogConfig(
                name="Private",
                url="https://example.test/opds",
                auth={"username": "alice", "password": "secret"},
            )
        ],
        preferences={},
    )

    redacted = redact_config(config)

    assert "secret" not in redacted
    assert "***" in redacted


def test_default_config_path_uses_appdata_on_windows(tmp_path: Path) -> None:
    path = default_config_path(env={"APPDATA": str(tmp_path)}, platform_name="nt")

    assert path == tmp_path / "epub-tui" / "config.json"


def test_default_config_path_uses_xdg_config_home(tmp_path: Path) -> None:
    path = default_config_path(
        env={"XDG_CONFIG_HOME": str(tmp_path)},
        platform_name="posix",
        home=tmp_path / "home",
    )

    assert path == tmp_path / "epub-tui" / "config.json"


def test_default_config_path_falls_back_to_linux_home(tmp_path: Path) -> None:
    path = default_config_path(env={}, platform_name="posix", home=tmp_path / "home")

    assert path == tmp_path / "home" / ".config" / "epub-tui" / "config.json"
