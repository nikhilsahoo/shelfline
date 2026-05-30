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


def test_load_config_extracts_embedded_url_credentials(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    library_path = tmp_path / "library"
    config_path.write_text(
        json.dumps(
            {
                "library_path": str(library_path),
                "catalogs": [
                    {
                        "name": "Private",
                        "url": "https://alice:secret@example.test/opds",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.catalogs[0].url == "https://example.test/opds"
    assert config.catalogs[0].auth == {"username": "alice", "password": "secret"}


def test_load_config_prefers_explicit_auth_over_embedded_url_credentials(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "library_path": str(tmp_path / "library"),
                "catalogs": [
                    {
                        "name": "Private",
                        "url": "https://ignored:ignored@example.test/opds",
                        "auth": {"username": "alice", "password": "secret"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.catalogs[0].url == "https://example.test/opds"
    assert config.catalogs[0].auth == {"username": "alice", "password": "secret"}


def test_save_and_redact_config_do_not_persist_embedded_url_credentials(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "library_path": str(tmp_path / "library"),
                "catalogs": [
                    {
                        "name": "Private",
                        "url": "https://alice:secret@example.test/opds",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config = load_config(config_path)
    saved_path = tmp_path / "saved.json"

    save_config(saved_path, config)
    saved = saved_path.read_text(encoding="utf-8")
    redacted = redact_config(config)

    assert "https://example.test/opds" in saved
    assert "https://example.test/opds" in redacted
    assert "alice" not in saved
    assert "secret" not in saved
    assert "alice" not in redacted
    assert "secret" not in redacted


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


def test_save_config_restricts_open_file_descriptor_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    real_fdopen = os.fdopen

    class RecordingFile:
        def __init__(self, file: object) -> None:
            self._file = file

        def __enter__(self) -> "RecordingFile":
            self._file.__enter__()
            return self

        def __exit__(self, *args: object) -> object:
            return self._file.__exit__(*args)

        def write(self, text: str) -> object:
            events.append("write")
            return self._file.write(text)

        def __getattr__(self, name: str) -> object:
            return getattr(self._file, name)

    def fake_fchmod(fd: int, mode: int) -> None:
        events.append(f"fchmod:{mode:o}")

    def recording_fdopen(fd: int, *args: object, **kwargs: object) -> RecordingFile:
        return RecordingFile(real_fdopen(fd, *args, **kwargs))

    monkeypatch.setattr("epub_tui.config.os.name", "posix")
    monkeypatch.setattr("epub_tui.config.os.fchmod", fake_fchmod, raising=False)
    monkeypatch.setattr("epub_tui.config.os.fdopen", recording_fdopen)

    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[
            CatalogConfig(
                name="Private",
                url="https://example.test/opds",
                auth={"username": "alice", "password": "secret"},
            )
        ],
    )

    save_config(config_path, config)

    assert events[:2] == ["fchmod:600", "write"]


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


def test_save_config_tightens_existing_permissive_file_on_posix(tmp_path: Path) -> None:
    if os.name != "posix":
        pytest.skip("POSIX permission bits are not meaningful on this platform")

    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")
    config_path.chmod(0o644)
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[
            CatalogConfig(
                name="Private",
                url="https://example.test/opds",
                auth={"username": "alice", "password": "secret"},
            )
        ],
    )

    save_config(config_path, config)

    assert config_path.stat().st_mode & 0o777 == 0o600
    assert "secret" in config_path.read_text(encoding="utf-8")


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
