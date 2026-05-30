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
class AppConfig:
    library_path: Path
    catalogs: list[CatalogConfig] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)


def default_config_path(
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
    home: Path | None = None,
) -> Path:
    values = os.environ if env is None else env
    system = os.name if platform_name is None else platform_name
    if system == "nt" and values.get("APPDATA"):
        return Path(values["APPDATA"]) / "epub-tui" / "config.json"
    if values.get("XDG_CONFIG_HOME"):
        return Path(values["XDG_CONFIG_HOME"]) / "epub-tui" / "config.json"
    return (home or Path.home()) / ".config" / "epub-tui" / "config.json"


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
        "preferences": config.preferences,
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _write_config_text(path, text)


def redact_config(config: AppConfig) -> str:
    payload = {
        "library_path": str(config.library_path),
        "catalogs": [_catalog_to_json(catalog, redact=True) for catalog in config.catalogs],
        "preferences": config.preferences,
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

    preferences = raw.get("preferences", {})
    if not isinstance(preferences, dict):
        raise ConfigError("preferences must be an object")

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
        if not isinstance(username, str) or not isinstance(password, str):
            raise ConfigError(f"Catalog {name} auth requires both username and password")
        auth = {"username": username, "password": password}
    elif embedded_auth is not None:
        auth = embedded_auth
        auth_from_url = True

    return CatalogConfig(name=name, url=sanitized_url, auth=auth, auth_from_url=auth_from_url)


def _catalog_to_json(catalog: CatalogConfig, redact: bool = False) -> dict[str, Any]:
    item: dict[str, Any] = {"name": catalog.name, "url": _strip_url_credentials(catalog.url)}
    if catalog.auth is not None and not catalog.auth_from_url:
        item["auth"] = {
            "username": catalog.auth["username"],
            "password": "***" if redact else catalog.auth["password"],
        }
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
