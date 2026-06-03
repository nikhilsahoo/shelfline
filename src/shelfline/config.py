from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import unquote, urlparse, urlsplit, urlunsplit


class ConfigError(ValueError):
    pass


_CONFIG_FILE_MODE = 0o600


@dataclass(frozen=True)
class CatalogConfig:
    name: str
    url: str
    auth: dict[str, str] | None = None
    auth_from_url: bool = field(default=False, repr=False, compare=False)


@dataclass(frozen=True)
class ReaderPreferences:
    width: str = "medium"
    theme: str = "default"
    paragraph_spacing: str = "normal"
    show_progress: bool = True
    show_chapter_title: bool = True
    zen_mode_default: bool = False


@dataclass(frozen=True)
class CoverPreferences:
    display: str = "auto"
    prefer_thumbnails: bool = True
    renderer: str = "auto"


@dataclass(frozen=True, eq=False)
class AppPreferences:
    reader: ReaderPreferences = field(default_factory=ReaderPreferences)
    covers: CoverPreferences = field(default_factory=CoverPreferences)
    extra: dict[str, Any] = field(default_factory=dict)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, dict):
            return self.extra == other
        if not isinstance(other, AppPreferences):
            return NotImplemented
        return (
            self.reader == other.reader
            and self.covers == other.covers
            and self.extra == other.extra
        )


@dataclass(frozen=True)
class AppConfig:
    library_path: Path
    catalogs: list[CatalogConfig] = field(default_factory=list)
    preferences: AppPreferences | dict[str, Any] = field(default_factory=AppPreferences)

    def __post_init__(self) -> None:
        if isinstance(self.preferences, AppPreferences):
            return
        object.__setattr__(self, "preferences", _parse_preferences(self.preferences))


_READER_WIDTHS = {"narrow", "medium", "wide"}
_READER_THEMES = {"default", "warm", "high_contrast"}
_PARAGRAPH_SPACING = {"compact", "normal", "relaxed"}
_COVER_DISPLAY = {"auto", "text", "off"}
_COVER_RENDERERS = {"auto", "tgp", "sixel", "halfcell", "unicode", "text"}


def default_config_path(
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> Path:
    values = os.environ if env is None else env
    system = os.name if platform_name is None else platform_name
    if system == "nt" and values.get("APPDATA"):
        return Path(values["APPDATA"]) / "shelfline" / "config.json"
    if values.get("XDG_CONFIG_HOME"):
        return Path(values["XDG_CONFIG_HOME"]) / "shelfline" / "config.json"
    return (home or Path.home()) / ".config" / "shelfline" / "config.json"


def load_config(path: Path) -> AppConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Malformed JSON config: {exc.msg}") from exc
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file does not exist: {path}") from exc

    return _parse_config(raw)


def save_config(path: Path, config: AppConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "library_path": str(config.library_path),
        "catalogs": [_catalog_to_json(catalog) for catalog in config.catalogs],
        "preferences": _preferences_to_json(config.preferences),
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _write_config_text(path, text)


def redact_config(config: AppConfig) -> str:
    payload = {
        "library_path": str(config.library_path),
        "catalogs": [_catalog_to_json(catalog, redact=True) for catalog in config.catalogs],
        "preferences": _preferences_to_json(config.preferences),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _parse_config(raw: Any) -> AppConfig:
    if not isinstance(raw, dict):
        raise ConfigError("Config root must be a JSON object")

    library_value = raw.get("library_path")
    if not isinstance(library_value, str) or not library_value.strip():
        raise ConfigError("library_path must be a non-empty string")

    catalogs_raw = raw.get("catalogs", [])
    if not isinstance(catalogs_raw, list):
        raise ConfigError("catalogs must be a list")

    seen_names: set[str] = set()
    catalogs: list[CatalogConfig] = []
    for item in catalogs_raw:
        catalog = _parse_catalog(item)
        if catalog.name in seen_names:
            raise ConfigError(f"Duplicate catalog name: {catalog.name}")
        seen_names.add(catalog.name)
        catalogs.append(catalog)

    preferences = _parse_preferences(raw.get("preferences", {}))

    return AppConfig(
        library_path=Path(library_value).expanduser(),
        catalogs=catalogs,
        preferences=preferences,
    )


def _parse_catalog(raw: Any) -> CatalogConfig:
    if not isinstance(raw, dict):
        raise ConfigError("catalog entries must be objects")

    name = raw.get("name")
    url = raw.get("url")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("catalog name must be a non-empty string")
    if not isinstance(url, str) or not _is_http_url(url):
        raise ConfigError(f"Invalid catalog URL for {name}")

    sanitized_url, embedded_auth = _normalize_catalog_url(url)
    auth_raw = raw.get("auth")
    auth: dict[str, str] | None = None
    auth_from_url = False
    if auth_raw is not None:
        if not isinstance(auth_raw, dict):
            raise ConfigError(f"Catalog {name} auth must be an object")
        username = auth_raw.get("username")
        password = auth_raw.get("password")
        password_ref = auth_raw.get("password_ref")
        if not isinstance(username, str):
            raise ConfigError(f"Catalog {name} auth requires username")
        if "password" in auth_raw and not isinstance(password, str):
            raise ConfigError(f"Catalog {name} auth password must be a string")
        if "password_ref" in auth_raw and not isinstance(password_ref, str):
            raise ConfigError(f"Catalog {name} auth password_ref must be a string")
        if not isinstance(password, str) and not isinstance(password_ref, str):
            raise ConfigError(f"Catalog {name} auth requires password or password_ref")
        auth = {"username": username}
        if isinstance(password, str):
            auth["password"] = password
        if isinstance(password_ref, str):
            auth["password_ref"] = password_ref
    elif embedded_auth is not None:
        auth = embedded_auth
        auth_from_url = True

    return CatalogConfig(name=name, url=sanitized_url, auth=auth, auth_from_url=auth_from_url)


def _parse_preferences(raw: Any) -> AppPreferences:
    if raw is None:
        return AppPreferences()
    if not isinstance(raw, dict):
        raise ConfigError("preferences must be an object")

    known = {"reader", "covers"}
    extra = {key: value for key, value in raw.items() if key not in known}
    return AppPreferences(
        reader=_parse_reader_preferences(raw.get("reader", {})),
        covers=_parse_cover_preferences(raw.get("covers", {})),
        extra=extra,
    )


def _parse_reader_preferences(raw: Any) -> ReaderPreferences:
    if not isinstance(raw, dict):
        raise ConfigError("preferences.reader must be an object")
    return ReaderPreferences(
        width=_enum_value(raw, "width", "medium", _READER_WIDTHS, "preferences.reader.width"),
        theme=_enum_value(raw, "theme", "default", _READER_THEMES, "preferences.reader.theme"),
        paragraph_spacing=_enum_value(
            raw,
            "paragraph_spacing",
            "normal",
            _PARAGRAPH_SPACING,
            "preferences.reader.paragraph_spacing",
        ),
        show_progress=_bool_value(raw, "show_progress", True, "preferences.reader.show_progress"),
        show_chapter_title=_bool_value(
            raw,
            "show_chapter_title",
            True,
            "preferences.reader.show_chapter_title",
        ),
        zen_mode_default=_bool_value(
            raw,
            "zen_mode_default",
            False,
            "preferences.reader.zen_mode_default",
        ),
    )


def _parse_cover_preferences(raw: Any) -> CoverPreferences:
    if not isinstance(raw, dict):
        raise ConfigError("preferences.covers must be an object")
    return CoverPreferences(
        display=_enum_value(raw, "display", "auto", _COVER_DISPLAY, "preferences.covers.display"),
        prefer_thumbnails=_bool_value(
            raw,
            "prefer_thumbnails",
            True,
            "preferences.covers.prefer_thumbnails",
        ),
        renderer=_enum_value(
            raw,
            "renderer",
            "auto",
            _COVER_RENDERERS,
            "preferences.covers.renderer",
        ),
    )


def _enum_value(raw: dict[str, Any], key: str, default: str, allowed: set[str], label: str) -> str:
    value = raw.get(key, default)
    if not isinstance(value, str) or value not in allowed:
        raise ConfigError(f"{label} must be one of: {', '.join(sorted(allowed))}")
    return value


def _bool_value(raw: dict[str, Any], key: str, default: bool, label: str) -> bool:
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{label} must be true or false")
    return value


def _preferences_to_json(preferences: AppPreferences) -> dict[str, Any]:
    if isinstance(preferences, dict):
        preferences = _parse_preferences(preferences)
    payload: dict[str, Any] = dict(preferences.extra)
    payload["reader"] = {
        "width": preferences.reader.width,
        "theme": preferences.reader.theme,
        "paragraph_spacing": preferences.reader.paragraph_spacing,
        "show_progress": preferences.reader.show_progress,
        "show_chapter_title": preferences.reader.show_chapter_title,
        "zen_mode_default": preferences.reader.zen_mode_default,
    }
    payload["covers"] = {
        "display": preferences.covers.display,
        "prefer_thumbnails": preferences.covers.prefer_thumbnails,
        "renderer": preferences.covers.renderer,
    }
    return payload


def _catalog_to_json(catalog: CatalogConfig, redact: bool = False) -> dict[str, Any]:
    item: dict[str, Any] = {"name": catalog.name, "url": _strip_url_credentials(catalog.url)}
    if catalog.auth is not None:
        auth: dict[str, str] = {"username": catalog.auth["username"]}
        if "password" in catalog.auth:
            auth["password"] = "***" if redact else catalog.auth["password"]
        if "password_ref" in catalog.auth:
            auth["password_ref"] = catalog.auth["password_ref"]
        item["auth"] = auth
    return item


def _write_config_text(path: Path, text: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT
    fd = os.open(path, flags, _CONFIG_FILE_MODE)
    try:
        _restrict_config_descriptor_permissions(fd)
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            fd = -1
            file.write(text)
    finally:
        if fd != -1:
            os.close(fd)
    _restrict_config_permissions(path)


def _restrict_config_descriptor_permissions(fd: int) -> None:
    if os.name != "posix":
        return
    fchmod = getattr(os, "fchmod", None)
    if fchmod is None:
        return
    try:
        fchmod(fd, _CONFIG_FILE_MODE)
    except (OSError, NotImplementedError):
        pass


def _restrict_config_permissions(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        os.chmod(path, _CONFIG_FILE_MODE)
    except (OSError, NotImplementedError):
        pass


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalize_catalog_url(url: str) -> tuple[str, dict[str, str] | None]:
    parts = urlsplit(url)
    auth = None
    if parts.username is not None:
        auth = {
            "username": unquote(parts.username),
            "password": unquote(parts.password or ""),
        }
    return _strip_url_credentials(url), auth


def _strip_url_credentials(url: str) -> str:
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url

    hostname = parts.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
