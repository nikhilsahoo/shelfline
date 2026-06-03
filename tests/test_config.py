import json
import os
from pathlib import Path

import pytest

from shelfline.config import (
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


def test_load_config_with_catalog_auth_password_ref(tmp_path: Path) -> None:
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
                        "auth": {"username": "alice", "password_ref": "shelfline:Private"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.catalogs[0].auth == {
        "username": "alice",
        "password_ref": "shelfline:Private",
    }


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

    saved_payload = json.loads(saved)
    redacted_payload = json.loads(redacted)

    assert saved_payload["catalogs"][0] == {
        "name": "Private",
        "url": "https://example.test/opds",
        "auth": {"username": "alice", "password": "secret"},
    }
    assert redacted_payload["catalogs"][0] == {
        "name": "Private",
        "url": "https://example.test/opds",
        "auth": {"username": "alice", "password": "***"},
    }
    assert "alice:secret@" not in saved
    assert "alice:secret@" not in redacted
    assert "secret" not in redacted


def test_save_and_redact_config_preserve_password_ref_without_secret(tmp_path: Path) -> None:
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[
            CatalogConfig(
                name="Private",
                url="https://example.test/opds",
                auth={"username": "alice", "password_ref": "shelfline:Private"},
            )
        ],
    )
    saved_path = tmp_path / "saved.json"

    save_config(saved_path, config)
    saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))
    redacted_payload = json.loads(redact_config(config))

    expected_catalog = {
        "name": "Private",
        "url": "https://example.test/opds",
        "auth": {"username": "alice", "password_ref": "shelfline:Private"},
    }
    assert saved_payload["catalogs"][0] == expected_catalog
    assert redacted_payload["catalogs"][0] == expected_catalog
    assert "password" not in saved_payload["catalogs"][0]["auth"]
    assert "password" not in redacted_payload["catalogs"][0]["auth"]


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


def test_default_preferences_are_loaded_when_missing(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    books = tmp_path / "books"
    books.mkdir()
    path.write_text(json.dumps({"library_path": str(books)}), encoding="utf-8")

    config = load_config(path)

    assert config.preferences.reader.width == "medium"
    assert config.preferences.reader.theme == "default"
    assert config.preferences.reader.paragraph_spacing == "normal"
    assert config.preferences.reader.show_progress is True
    assert config.preferences.reader.show_chapter_title is True
    assert config.preferences.reader.zen_mode_default is False
    assert config.preferences.covers.display == "auto"
    assert config.preferences.covers.prefer_thumbnails is True
    assert config.preferences.covers.renderer == "auto"


def test_app_config_normalizes_raw_preference_dicts(tmp_path: Path) -> None:
    config = AppConfig(
        library_path=tmp_path / "books",
        preferences={
            "reader": {"width": "wide"},
            "covers": {"display": "text", "renderer": "sixel"},
            "theme": "textual-dark",
        },
    )

    assert config.preferences.reader.width == "wide"
    assert config.preferences.reader.theme == "default"
    assert config.preferences.covers.display == "text"
    assert config.preferences.covers.renderer == "sixel"
    assert config.preferences.extra == {"theme": "textual-dark"}


def test_reader_and_cover_preferences_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    books = tmp_path / "books"
    books.mkdir()
    path.write_text(
        json.dumps(
            {
                "library_path": str(books),
                "preferences": {
                    "reader": {
                        "width": "wide",
                        "theme": "warm",
                        "paragraph_spacing": "relaxed",
                        "show_progress": False,
                        "show_chapter_title": False,
                        "zen_mode_default": True,
                    },
                    "covers": {
                        "display": "text",
                        "prefer_thumbnails": False,
                        "renderer": "tgp",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_config(path)
    save_config(path, config)
    saved = json.loads(path.read_text(encoding="utf-8"))

    assert saved["preferences"]["reader"]["width"] == "wide"
    assert saved["preferences"]["reader"]["theme"] == "warm"
    assert saved["preferences"]["reader"]["paragraph_spacing"] == "relaxed"
    assert saved["preferences"]["reader"]["show_progress"] is False
    assert saved["preferences"]["reader"]["show_chapter_title"] is False
    assert saved["preferences"]["reader"]["zen_mode_default"] is True
    assert saved["preferences"]["covers"]["display"] == "text"
    assert saved["preferences"]["covers"]["prefer_thumbnails"] is False
    assert saved["preferences"]["covers"]["renderer"] == "tgp"


def test_unknown_preference_keys_survive_save_and_redact(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    books = tmp_path / "books"
    books.mkdir()
    path.write_text(
        json.dumps(
            {
                "library_path": str(books),
                "preferences": {
                    "reader": {"width": "narrow"},
                    "covers": {"display": "off"},
                    "theme": "textual-dark",
                    "custom": {"accent": "green"},
                },
            }
        ),
        encoding="utf-8",
    )

    config = load_config(path)
    save_config(path, config)
    saved = json.loads(path.read_text(encoding="utf-8"))
    redacted = json.loads(redact_config(config))

    assert saved["preferences"]["theme"] == "textual-dark"
    assert saved["preferences"]["custom"] == {"accent": "green"}
    assert redacted["preferences"]["theme"] == "textual-dark"
    assert redacted["preferences"]["custom"] == {"accent": "green"}


def test_redact_config_serializes_typed_preferences_and_extra_values(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    books = tmp_path / "books"
    books.mkdir()
    path.write_text(
        json.dumps(
            {
                "library_path": str(books),
                "preferences": {
                    "reader": {
                        "width": "wide",
                        "theme": "high_contrast",
                        "paragraph_spacing": "compact",
                        "show_progress": False,
                        "show_chapter_title": False,
                        "zen_mode_default": True,
                    },
                    "covers": {
                        "display": "text",
                        "prefer_thumbnails": False,
                        "renderer": "unicode",
                    },
                    "ui_density": "compact",
                },
            }
        ),
        encoding="utf-8",
    )

    redacted = json.loads(redact_config(load_config(path)))

    assert redacted["preferences"]["reader"] == {
        "width": "wide",
        "theme": "high_contrast",
        "paragraph_spacing": "compact",
        "show_progress": False,
        "show_chapter_title": False,
        "zen_mode_default": True,
    }
    assert redacted["preferences"]["covers"] == {
        "display": "text",
        "prefer_thumbnails": False,
        "renderer": "unicode",
    }
    assert redacted["preferences"]["ui_density"] == "compact"


def test_add_catalog_preserves_typed_preferences_from_loaded_config(tmp_path: Path) -> None:
    from shelfline.app import ShelflineApp

    path = tmp_path / "config.json"
    books = tmp_path / "books"
    books.mkdir()
    path.write_text(
        json.dumps(
            {
                "library_path": str(books),
                "preferences": {
                    "reader": {"width": "wide"},
                    "covers": {"display": "text", "renderer": "halfcell"},
                    "theme": "textual-dark",
                },
            }
        ),
        encoding="utf-8",
    )
    app = ShelflineApp(config=load_config(path))

    app.add_catalog(CatalogConfig(name="Public", url="https://example.test/opds"))

    assert app.config is not None
    assert app.config.preferences.reader.width == "wide"
    assert app.config.preferences.covers.display == "text"
    assert app.config.preferences.covers.renderer == "halfcell"
    assert app.config.preferences.extra == {"theme": "textual-dark"}


def test_cover_renderer_preference_accepts_supported_values(tmp_path: Path) -> None:
    books = tmp_path / "books"
    books.mkdir()

    for renderer in ["auto", "tgp", "sixel", "halfcell", "unicode", "text"]:
        path = tmp_path / f"{renderer}.json"
        path.write_text(
            json.dumps(
                {
                    "library_path": str(books),
                    "preferences": {"covers": {"renderer": renderer}},
                }
            ),
            encoding="utf-8",
        )

        config = load_config(path)

        assert config.preferences.covers.renderer == renderer


def test_invalid_cover_renderer_preference_fails(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    books = tmp_path / "books"
    books.mkdir()
    path.write_text(
        json.dumps(
            {
                "library_path": str(books),
                "preferences": {"covers": {"renderer": "pixel-perfect"}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="preferences.covers.renderer"):
        load_config(path)


def test_invalid_known_reader_preference_fails(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    books = tmp_path / "books"
    books.mkdir()
    path.write_text(
        json.dumps(
            {
                "library_path": str(books),
                "preferences": {"reader": {"width": "cinema"}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="preferences.reader.width"):
        load_config(path)


def test_invalid_known_cover_preference_fails(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    books = tmp_path / "books"
    books.mkdir()
    path.write_text(
        json.dumps(
            {
                "library_path": str(books),
                "preferences": {"covers": {"display": "always"}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="preferences.covers.display"):
        load_config(path)


def test_save_config_restricts_file_permissions_when_supported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chmod_calls: list[tuple[Path, int]] = []

    def fake_chmod(path: Path, mode: int) -> None:
        chmod_calls.append((path, mode))

    monkeypatch.setattr("shelfline.config.os.name", "posix")
    monkeypatch.setattr("shelfline.config.os.chmod", fake_chmod)

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

    monkeypatch.setattr("shelfline.config.os.name", "posix")
    monkeypatch.setattr("shelfline.config.os.fchmod", fake_fchmod, raising=False)
    monkeypatch.setattr("shelfline.config.os.fdopen", recording_fdopen)

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

    with pytest.raises(ConfigError, match="requires password or password_ref"):
        load_config(config_path)


def test_rejects_non_string_auth_password_even_with_password_ref(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "library_path": str(tmp_path / "library"),
                "catalogs": [
                    {
                        "name": "Broken",
                        "url": "https://example.test/opds",
                        "auth": {
                            "username": "alice",
                            "password": 123,
                            "password_ref": "shelfline:Broken",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="password must be a string"):
        load_config(config_path)


def test_rejects_non_string_auth_password_ref_even_with_password(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "library_path": str(tmp_path / "library"),
                "catalogs": [
                    {
                        "name": "Broken",
                        "url": "https://example.test/opds",
                        "auth": {
                            "username": "alice",
                            "password": "secret",
                            "password_ref": 123,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="password_ref must be a string"):
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

    assert path == tmp_path / "shelfline" / "config.json"


def test_default_config_path_uses_xdg_config_home(tmp_path: Path) -> None:
    path = default_config_path(
        env={"XDG_CONFIG_HOME": str(tmp_path)},
        platform_name="posix",
        home=tmp_path / "home",
    )

    assert path == tmp_path / "shelfline" / "config.json"


def test_default_config_path_falls_back_to_linux_home(tmp_path: Path) -> None:
    path = default_config_path(env={}, platform_name="posix", home=tmp_path / "home")

    assert path == tmp_path / "home" / ".config" / "shelfline" / "config.json"
