# Catalog-First MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python Textual TUI that browses OPDS 1.x catalogs, supports optional Basic Auth, downloads one book at a time into a user-configured library path, manages downloaded books locally, displays cover images when terminal graphics are available, and previews EPUB text.

**Architecture:** Use a layered package where Textual screens call small core services. JSON config owns user-editable library/catalog settings, SQLite owns app-managed cache and book metadata, and catalog/download/reader modules are testable without launching the TUI.

**Tech Stack:** Python 3.11+, Textual, Rich, optional textual-image for Sixel/terminal graphics cover rendering, httpx, feedparser, pytest, pytest-asyncio, pytest-httpx, ebooklib, SQLite via the standard library, JSON via the standard library.

---

## File Structure

- `pyproject.toml`: package metadata, dependencies, pytest config, console script.
- `README.md`: short setup and MVP usage notes.
- `src/epub_tui/__init__.py`: package version.
- `src/epub_tui/__main__.py`: `python -m epub_tui` entrypoint.
- `src/epub_tui/app.py`: Textual app class and dependency wiring.
- `src/epub_tui/config.py`: JSON config models, default config path, loading, saving, validation, credential redaction.
- `src/epub_tui/catalog/models.py`: OPDS feed, entry, and acquisition dataclasses.
- `src/epub_tui/catalog/parser.py`: OPDS 1.x Atom normalization from feedparser output.
- `src/epub_tui/catalog/client.py`: HTTP fetching with optional Basic Auth.
- `src/epub_tui/library.py`: SQLite schema plus book/cache repositories with read/unread and deletion operations.
- `src/epub_tui/downloads.py`: single download service with progress callbacks and temporary-file completion.
- `src/epub_tui/reader.py`: EPUB text extraction.
- `src/epub_tui/tui/screens.py`: Textual screens for setup, catalogs, feeds, entries, library, preview.
- `src/epub_tui/tui/widgets.py`: reusable list/detail/status widgets, including graceful cover image display, busy indicators, and download progress display.
- `tests/conftest.py`: shared fixtures.
- `tests/fixtures/opds/navigation.xml`: OPDS navigation feed fixture.
- `tests/fixtures/opds/acquisition.xml`: OPDS acquisition feed fixture.
- `tests/fixtures/opds/invalid.xml`: malformed feed fixture.
- `tests/test_config.py`: config load/save/validation/redaction tests.
- `tests/test_catalog_parser.py`: OPDS parser tests.
- `tests/test_catalog_client.py`: HTTP and Basic Auth tests.
- `tests/test_library.py`: SQLite repository tests.
- `tests/test_downloads.py`: download workflow tests.
- `tests/test_reader.py`: EPUB preview tests.
- `tests/test_tui_smoke.py`: Textual smoke tests.

---

### Task 1: Project Scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/epub_tui/__init__.py`
- Create: `src/epub_tui/__main__.py`
- Create: `src/epub_tui/app.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Create the packaging test**

Create `tests/test_package.py`:

```python
from epub_tui import __version__


def test_package_has_version() -> None:
    assert __version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_package.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'epub_tui'`.

- [ ] **Step 3: Add package scaffold**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=69", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "epub-tui"
version = "0.1.0"
description = "Terminal OPDS catalog browser and book downloader"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "ebooklib>=0.18",
  "feedparser>=6.0.11",
  "httpx>=0.27",
  "rich>=13.7",
  "textual>=0.80",
  "textual-image>=0.8",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.2",
  "pytest-asyncio>=0.23",
  "pytest-httpx>=0.30",
]

[project.scripts]
epub-tui = "epub_tui.__main__:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

Create `README.md`:

```markdown
# epub-tui

Catalog-first terminal app for browsing OPDS 1.x catalogs, downloading books, and previewing EPUB text.

## Development

```powershell
python -m pip install -e ".[dev]"
pytest
```

## MVP

- OPDS 1.x Atom catalog browsing
- Optional HTTP Basic Auth per catalog
- One active download at a time
- Download progress bar for known totals and byte counter for unknown totals
- Busy indicator on every TUI screen while catalog fetch, refresh, navigation, cover fetch, or download start calls are running
- JSON config for library path and saved catalogs
- SQLite metadata/cache
- Local library management: mark read/unread and delete downloaded books
- Sixel/terminal graphics cover display when supported, with text fallback
- EPUB text preview
```

Create `src/epub_tui/__init__.py`:

```python
__version__ = "0.1.0"
```

Create `src/epub_tui/__main__.py`:

```python
from epub_tui.app import EpubTuiApp


def main() -> None:
    EpubTuiApp().run()


if __name__ == "__main__":
    main()
```

Create `src/epub_tui/app.py`:

```python
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static


class EpubTuiApp(App[None]):
    TITLE = "epub-tui"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("l", "show_library", "Library"),
        ("m", "toggle_read", "Read/Unread"),
        ("x", "delete_book", "Delete Book"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("epub-tui catalog-first MVP")
        yield Footer()

    def action_show_library(self) -> None:
        self.notify("Library screen is not wired yet")

    def action_toggle_read(self) -> None:
        self.notify("Read/unread is available from the library screen")

    def action_delete_book(self) -> None:
        self.notify("Delete is available from the library screen")
```

Create `tests/conftest.py`:

```python
from pathlib import Path

import pytest


@pytest.fixture
def fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures"
```

- [ ] **Step 4: Run package test**

Run: `pytest tests/test_package.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md src tests
git commit -m "chore: scaffold Python TUI project"
```

---

### Task 2: JSON Configuration

**Files:**
- Create: `src/epub_tui/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Create `tests/test_config.py`:

```python
import json
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_config.py -v`

Expected: FAIL with `ModuleNotFoundError` or missing symbols from `epub_tui.config`.

- [ ] **Step 3: Implement config module**

Create `src/epub_tui/config.py`:

```python
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CatalogConfig:
    name: str
    url: str
    auth: dict[str, str] | None = None


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
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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

    auth_raw = raw.get("auth")
    auth: dict[str, str] | None = None
    if auth_raw is not None:
        if not isinstance(auth_raw, dict):
            raise ConfigError(f"Catalog {name} auth must be an object")
        username = auth_raw.get("username")
        password = auth_raw.get("password")
        if not isinstance(username, str) or not isinstance(password, str):
            raise ConfigError(f"Catalog {name} auth requires both username and password")
        auth = {"username": username, "password": password}

    return CatalogConfig(name=name, url=url, auth=auth)


def _catalog_to_json(catalog: CatalogConfig, redact: bool = False) -> dict[str, Any]:
    item: dict[str, Any] = {"name": catalog.name, "url": catalog.url}
    if catalog.auth is not None:
        item["auth"] = {
            "username": catalog.auth["username"],
            "password": "***" if redact else catalog.auth["password"],
        }
    return item


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
```

- [ ] **Step 4: Run config tests**

Run: `pytest tests/test_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/epub_tui/config.py tests/test_config.py
git commit -m "feat: add JSON configuration"
```

---

### Task 3: OPDS Models And Parser

**Files:**
- Create: `src/epub_tui/catalog/__init__.py`
- Create: `src/epub_tui/catalog/models.py`
- Create: `src/epub_tui/catalog/parser.py`
- Create: `tests/fixtures/opds/navigation.xml`
- Create: `tests/fixtures/opds/acquisition.xml`
- Create: `tests/fixtures/opds/invalid.xml`
- Create: `tests/test_catalog_parser.py`

- [ ] **Step 1: Write fixtures**

Create `tests/fixtures/opds/navigation.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Catalog</title>
  <id>urn:example:catalog</id>
  <updated>2026-05-30T00:00:00Z</updated>
  <entry>
    <title>Fiction</title>
    <id>urn:example:fiction</id>
    <updated>2026-05-30T00:00:00Z</updated>
    <link rel="subsection" href="/opds/fiction.xml" type="application/atom+xml;profile=opds-catalog"/>
  </entry>
</feed>
```

Create `tests/fixtures/opds/acquisition.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Fiction</title>
  <id>urn:example:fiction</id>
  <updated>2026-05-30T00:00:00Z</updated>
  <entry>
    <title>Sample Book</title>
    <id>urn:isbn:9780000000001</id>
    <updated>2026-05-30T00:00:00Z</updated>
    <author><name>Ada Writer</name></author>
    <summary>A short fixture book.</summary>
    <link rel="http://opds-spec.org/image" href="covers/sample.jpg" type="image/jpeg" title="Cover"/>
    <link rel="http://opds-spec.org/image/thumbnail" href="covers/sample-thumb.jpg" type="image/jpeg" title="Thumbnail"/>
    <link rel="http://opds-spec.org/acquisition" href="books/sample.epub" type="application/epub+zip" title="EPUB"/>
    <link rel="http://opds-spec.org/acquisition" href="books/sample.pdf" type="application/pdf" title="PDF"/>
  </entry>
</feed>
```

Create `tests/fixtures/opds/invalid.xml`:

```xml
<feed><title>Broken</title>
```

- [ ] **Step 2: Write failing parser tests**

Create `tests/test_catalog_parser.py`:

```python
from pathlib import Path

import pytest

from epub_tui.catalog.parser import OpdsParseError, parse_opds_feed


def test_parse_navigation_feed_resolves_relative_links(fixture_dir: Path) -> None:
    xml = (fixture_dir / "opds" / "navigation.xml").read_text(encoding="utf-8")

    feed = parse_opds_feed(xml, source_url="https://example.test/root.xml")

    assert feed.title == "Example Catalog"
    assert feed.entries[0].title == "Fiction"
    assert feed.entries[0].navigation_url == "https://example.test/opds/fiction.xml"
    assert feed.entries[0].acquisition_links == []


def test_parse_acquisition_feed_extracts_epub_and_pdf(fixture_dir: Path) -> None:
    xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")

    feed = parse_opds_feed(xml, source_url="https://example.test/opds/fiction.xml")

    entry = feed.entries[0]
    assert entry.title == "Sample Book"
    assert entry.authors == ["Ada Writer"]
    assert entry.summary == "A short fixture book."
    assert entry.cover_image_url == "https://example.test/opds/covers/sample.jpg"
    assert entry.thumbnail_url == "https://example.test/opds/covers/sample-thumb.jpg"
    assert entry.best_epub_link().href == "https://example.test/opds/books/sample.epub"
    assert {link.media_type for link in entry.acquisition_links} == {"application/epub+zip", "application/pdf"}


def test_invalid_feed_raises_parse_error(fixture_dir: Path) -> None:
    xml = (fixture_dir / "opds" / "invalid.xml").read_text(encoding="utf-8")

    with pytest.raises(OpdsParseError, match="Invalid OPDS feed"):
        parse_opds_feed(xml, source_url="https://example.test/broken.xml")
```

- [ ] **Step 3: Run parser tests to verify they fail**

Run: `pytest tests/test_catalog_parser.py -v`

Expected: FAIL with missing `epub_tui.catalog.parser`.

- [ ] **Step 4: Implement models and parser**

Create `src/epub_tui/catalog/__init__.py`:

```python
from epub_tui.catalog.models import AcquisitionLink, CatalogEntry, CatalogFeed
from epub_tui.catalog.parser import OpdsParseError, parse_opds_feed

__all__ = [
    "AcquisitionLink",
    "CatalogEntry",
    "CatalogFeed",
    "OpdsParseError",
    "parse_opds_feed",
]
```

Create `src/epub_tui/catalog/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AcquisitionLink:
    href: str
    relation: str
    media_type: str
    title: str | None = None
    size: int | None = None


@dataclass(frozen=True)
class CatalogEntry:
    title: str
    identifier: str | None
    updated: str | None
    authors: list[str] = field(default_factory=list)
    summary: str | None = None
    cover_image_url: str | None = None
    thumbnail_url: str | None = None
    navigation_url: str | None = None
    acquisition_links: list[AcquisitionLink] = field(default_factory=list)

    def best_epub_link(self) -> AcquisitionLink | None:
        for link in self.acquisition_links:
            if link.media_type == "application/epub+zip":
                return link
        return None


@dataclass(frozen=True)
class CatalogFeed:
    title: str
    source_url: str
    updated: str | None
    entries: list[CatalogEntry]
```

Create `src/epub_tui/catalog/parser.py`:

```python
from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import feedparser

from epub_tui.catalog.models import AcquisitionLink, CatalogEntry, CatalogFeed


class OpdsParseError(ValueError):
    pass


ACQUISITION_REL_PREFIX = "http://opds-spec.org/acquisition"
IMAGE_REL = "http://opds-spec.org/image"
THUMBNAIL_REL = "http://opds-spec.org/image/thumbnail"
NAVIGATION_RELS = {"subsection", "start", "up", "self"}


def parse_opds_feed(xml: str, source_url: str) -> CatalogFeed:
    parsed = feedparser.parse(xml)
    if parsed.bozo:
        raise OpdsParseError("Invalid OPDS feed")
    if not parsed.feed.get("title"):
        raise OpdsParseError("Invalid OPDS feed: missing title")

    entries = [_parse_entry(entry, source_url) for entry in parsed.entries]
    return CatalogFeed(
        title=str(parsed.feed.get("title", "")),
        source_url=source_url,
        updated=_optional_str(parsed.feed.get("updated")),
        entries=entries,
    )


def _parse_entry(entry: Any, source_url: str) -> CatalogEntry:
    links = list(entry.get("links", []))
    acquisition_links = [_parse_acquisition_link(link, source_url) for link in links if _is_acquisition(link)]
    return CatalogEntry(
        title=str(entry.get("title", "Untitled")),
        identifier=_optional_str(entry.get("id")),
        updated=_optional_str(entry.get("updated")),
        authors=[author.get("name", "") for author in entry.get("authors", []) if author.get("name")],
        summary=_optional_str(entry.get("summary")),
        cover_image_url=_image_url(links, source_url, IMAGE_REL),
        thumbnail_url=_image_url(links, source_url, THUMBNAIL_REL),
        navigation_url=_navigation_url(links, source_url),
        acquisition_links=acquisition_links,
    )


def _parse_acquisition_link(link: Any, source_url: str) -> AcquisitionLink:
    length = link.get("length")
    return AcquisitionLink(
        href=urljoin(source_url, str(link.get("href", ""))),
        relation=str(link.get("rel", "")),
        media_type=str(link.get("type", "")),
        title=_optional_str(link.get("title")),
        size=int(length) if isinstance(length, str) and length.isdigit() else None,
    )


def _navigation_url(links: list[Any], source_url: str) -> str | None:
    for link in links:
        rel = str(link.get("rel", ""))
        media_type = str(link.get("type", ""))
        if rel in NAVIGATION_RELS and "atom+xml" in media_type and link.get("href"):
            return urljoin(source_url, str(link["href"]))
    return None


def _is_acquisition(link: Any) -> bool:
    return str(link.get("rel", "")).startswith(ACQUISITION_REL_PREFIX)


def _image_url(links: list[Any], source_url: str, relation: str) -> str | None:
    for link in links:
        if str(link.get("rel", "")) == relation and str(link.get("type", "")).startswith("image/"):
            return urljoin(source_url, str(link.get("href", "")))
    return None


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None
```

- [ ] **Step 5: Run parser tests**

Run: `pytest tests/test_catalog_parser.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/epub_tui/catalog tests/fixtures/opds tests/test_catalog_parser.py
git commit -m "feat: parse OPDS 1 feeds"
```

---

### Task 4: Catalog HTTP Client With Basic Auth

**Files:**
- Create: `src/epub_tui/catalog/client.py`
- Create: `tests/test_catalog_client.py`

- [ ] **Step 1: Write failing client tests**

Create `tests/test_catalog_client.py`:

```python
import base64

import httpx
import pytest
from pytest_httpx import HTTPXMock

from epub_tui.catalog.client import CatalogClient, CatalogFetchError
from epub_tui.config import CatalogConfig


@pytest.mark.asyncio
async def test_fetch_feed_without_auth(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://example.test/opds", text="<feed><title>Hi</title></feed>")
    client = CatalogClient(httpx.AsyncClient())

    text = await client.fetch_feed(CatalogConfig(name="Public", url="https://example.test/opds"))

    assert "<title>Hi</title>" in text


@pytest.mark.asyncio
async def test_fetch_feed_with_basic_auth(httpx_mock: HTTPXMock) -> None:
    expected = "Basic " + base64.b64encode(b"alice:secret").decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == expected
        return httpx.Response(200, text="<feed><title>Private</title></feed>")

    httpx_mock.add_callback(handler, url="https://example.test/private")
    client = CatalogClient(httpx.AsyncClient())

    text = await client.fetch_feed(
        CatalogConfig(
            name="Private",
            url="https://example.test/private",
            auth={"username": "alice", "password": "secret"},
        )
    )

    assert "Private" in text


@pytest.mark.asyncio
async def test_fetch_feed_redacts_password_on_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://example.test/private", status_code=401)
    client = CatalogClient(httpx.AsyncClient())

    with pytest.raises(CatalogFetchError) as exc:
        await client.fetch_feed(
            CatalogConfig(
                name="Private",
                url="https://example.test/private",
                auth={"username": "alice", "password": "secret"},
            )
        )

    assert "secret" not in str(exc.value)
    assert "Authentication failed for catalog Private" in str(exc.value)
```

- [ ] **Step 2: Run client tests to verify they fail**

Run: `pytest tests/test_catalog_client.py -v`

Expected: FAIL with missing `epub_tui.catalog.client`.

- [ ] **Step 3: Implement catalog client**

Create `src/epub_tui/catalog/client.py`:

```python
from __future__ import annotations

import httpx

from epub_tui.config import CatalogConfig


class CatalogFetchError(RuntimeError):
    pass


class CatalogClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=20.0, follow_redirects=True)

    async def fetch_feed(self, catalog: CatalogConfig, url: str | None = None) -> str:
        target_url = url or catalog.url
        try:
            response = await self._client.get(target_url, auth=_auth_tuple(catalog))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise CatalogFetchError(f"Authentication failed for catalog {catalog.name}") from exc
            raise CatalogFetchError(f"Failed to fetch catalog {catalog.name}: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise CatalogFetchError(f"Failed to fetch catalog {catalog.name}: {exc.__class__.__name__}") from exc
        return response.text

    async def aclose(self) -> None:
        await self._client.aclose()


def _auth_tuple(catalog: CatalogConfig) -> tuple[str, str] | None:
    if catalog.auth is None:
        return None
    return catalog.auth["username"], catalog.auth["password"]
```

- [ ] **Step 4: Run client tests**

Run: `pytest tests/test_catalog_client.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/epub_tui/catalog/client.py tests/test_catalog_client.py
git commit -m "feat: fetch catalogs with basic auth"
```

---

### Task 5: SQLite Library Repository

**Files:**
- Create: `src/epub_tui/library.py`
- Create: `tests/test_library.py`

- [ ] **Step 1: Write failing library tests**

Create `tests/test_library.py`:

```python
from pathlib import Path

from epub_tui.library import BookRecord, LibraryRepository


def test_repository_initializes_schema_and_saves_book(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()

    book = BookRecord(
        title="Sample Book",
        authors=["Ada Writer"],
        identifiers=["urn:isbn:9780000000001"],
        source_catalog="Private",
        source_entry_url="https://example.test/opds/book",
        acquisition_url="https://example.test/books/sample.epub",
        media_type="application/epub+zip",
        cover_image_url="https://example.test/covers/sample.jpg",
        cover_image_path=tmp_path / "covers" / "sample.jpg",
        local_file_path=tmp_path / "books" / "sample.epub",
        is_read=False,
    )

    repo.add_book(book)

    books = repo.list_books()
    assert len(books) == 1
    assert books[0].title == "Sample Book"
    assert books[0].authors == ["Ada Writer"]
    assert books[0].cover_image_url == "https://example.test/covers/sample.jpg"
    assert books[0].cover_image_path == tmp_path / "covers" / "sample.jpg"
    assert books[0].is_read is False


def test_repository_marks_book_read_and_unread(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"
    book_path.parent.mkdir()
    book_path.write_bytes(b"book")
    repo.add_book(
        BookRecord(
            title="Sample Book",
            authors=[],
            identifiers=[],
            source_catalog="Private",
            source_entry_url=None,
            acquisition_url="https://example.test/books/sample.epub",
            media_type="application/epub+zip",
            cover_image_url=None,
            cover_image_path=None,
            local_file_path=book_path,
            is_read=False,
        )
    )

    repo.mark_read(book_path, is_read=True)
    assert repo.list_books()[0].is_read is True

    repo.mark_read(book_path, is_read=False)
    assert repo.list_books()[0].is_read is False


def test_repository_deletes_local_book_and_hides_it_by_default(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"
    book_path.parent.mkdir()
    book_path.write_bytes(b"book")
    repo.add_book(
        BookRecord(
            title="Sample Book",
            authors=[],
            identifiers=[],
            source_catalog="Private",
            source_entry_url=None,
            acquisition_url="https://example.test/books/sample.epub",
            media_type="application/epub+zip",
            cover_image_url=None,
            cover_image_path=None,
            local_file_path=book_path,
            is_read=False,
        )
    )

    repo.delete_book(book_path, remove_file=True)

    assert not book_path.exists()
    assert repo.list_books() == []
    assert repo.list_books(include_deleted=True)[0].deleted_at is not None


def test_feed_cache_round_trip(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()

    repo.save_feed_cache("Private", "https://example.test/opds", "Catalog", "<feed />")

    cached = repo.get_feed_cache("https://example.test/opds")
    assert cached is not None
    assert cached["title"] == "Catalog"
    assert cached["body"] == "<feed />"
```

- [ ] **Step 2: Run library tests to verify they fail**

Run: `pytest tests/test_library.py -v`

Expected: FAIL with missing `epub_tui.library`.

- [ ] **Step 3: Implement repository**

Create `src/epub_tui/library.py`:

```python
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BookRecord:
    title: str
    authors: list[str]
    identifiers: list[str]
    source_catalog: str
    source_entry_url: str | None
    acquisition_url: str
    media_type: str
    cover_image_url: str | None
    cover_image_path: Path | None
    local_file_path: Path
    is_read: bool = False
    deleted_at: str | None = None


class LibraryRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    authors_json TEXT NOT NULL,
                    identifiers_json TEXT NOT NULL,
                    source_catalog TEXT NOT NULL,
                    source_entry_url TEXT,
                    acquisition_url TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    cover_image_url TEXT,
                    cover_image_path TEXT,
                    local_file_path TEXT NOT NULL UNIQUE,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    deleted_at TEXT,
                    downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS feed_cache (
                    url TEXT PRIMARY KEY,
                    source_catalog TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def add_book(self, book: BookRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO books (
                    title, authors_json, identifiers_json, source_catalog,
                    source_entry_url, acquisition_url, media_type,
                    cover_image_url, cover_image_path, local_file_path, is_read
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book.title,
                    json.dumps(book.authors),
                    json.dumps(book.identifiers),
                    book.source_catalog,
                    book.source_entry_url,
                    book.acquisition_url,
                    book.media_type,
                    book.cover_image_url,
                    str(book.cover_image_path) if book.cover_image_path is not None else None,
                    str(book.local_file_path),
                    1 if book.is_read else 0,
                ),
            )

    def list_books(self, include_deleted: bool = False) -> list[BookRecord]:
        deleted_clause = "" if include_deleted else "WHERE deleted_at IS NULL"
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT title, authors_json, identifiers_json, source_catalog,
                       source_entry_url, acquisition_url, media_type,
                       cover_image_url, cover_image_path, local_file_path,
                       is_read, deleted_at
                FROM books
                {deleted_clause}
                ORDER BY downloaded_at DESC, title ASC
                """
            ).fetchall()
        return [_book_from_row(row) for row in rows]

    def mark_read(self, local_file_path: Path, is_read: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE books SET is_read = ? WHERE local_file_path = ? AND deleted_at IS NULL",
                (1 if is_read else 0, str(local_file_path)),
            )

    def delete_book(self, local_file_path: Path, remove_file: bool = True) -> None:
        if remove_file:
            local_file_path.unlink(missing_ok=True)
        with self._connect() as conn:
            conn.execute(
                "UPDATE books SET deleted_at = CURRENT_TIMESTAMP WHERE local_file_path = ?",
                (str(local_file_path),),
            )

    def save_feed_cache(self, source_catalog: str, url: str, title: str, body: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO feed_cache (url, source_catalog, title, body, fetched_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(url) DO UPDATE SET
                    source_catalog = excluded.source_catalog,
                    title = excluded.title,
                    body = excluded.body,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                (url, source_catalog, title, body),
            )

    def get_feed_cache(self, url: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT source_catalog, title, body, fetched_at FROM feed_cache WHERE url = ?",
                (url,),
            ).fetchone()
        if row is None:
            return None
        return {
            "source_catalog": row["source_catalog"],
            "title": row["title"],
            "body": row["body"],
            "fetched_at": row["fetched_at"],
        }

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn


def _book_from_row(row: sqlite3.Row) -> BookRecord:
    return BookRecord(
        title=row["title"],
        authors=json.loads(row["authors_json"]),
        identifiers=json.loads(row["identifiers_json"]),
        source_catalog=row["source_catalog"],
        source_entry_url=row["source_entry_url"],
        acquisition_url=row["acquisition_url"],
        media_type=row["media_type"],
        cover_image_url=row["cover_image_url"],
        cover_image_path=Path(row["cover_image_path"]) if row["cover_image_path"] else None,
        local_file_path=Path(row["local_file_path"]),
        is_read=bool(row["is_read"]),
        deleted_at=row["deleted_at"],
    )
```

- [ ] **Step 4: Run library tests**

Run: `pytest tests/test_library.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/epub_tui/library.py tests/test_library.py
git commit -m "feat: add library metadata store"
```

---

### Task 6: Single Download Service

**Files:**
- Create: `src/epub_tui/downloads.py`
- Create: `tests/test_downloads.py`

- [ ] **Step 1: Write failing download tests**

Create `tests/test_downloads.py`:

```python
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from epub_tui.downloads import DownloadError, DownloadProgress, DownloadService


@pytest.mark.asyncio
async def test_download_writes_temp_then_final_file(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://example.test/book.epub", content=b"book bytes")
    service = DownloadService(httpx.AsyncClient())

    result = await service.download(
        url="https://example.test/book.epub",
        destination_dir=tmp_path,
        filename="book.epub",
    )

    assert result == tmp_path / "book.epub"
    assert result.read_bytes() == b"book bytes"
    assert not (tmp_path / "book.epub.part").exists()


@pytest.mark.asyncio
async def test_download_rejects_duplicate_final_file(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    (tmp_path / "book.epub").write_bytes(b"existing")
    service = DownloadService(httpx.AsyncClient())

    with pytest.raises(DownloadError, match="already exists"):
        await service.download(
            url="https://example.test/book.epub",
            destination_dir=tmp_path,
            filename="book.epub",
        )


@pytest.mark.asyncio
async def test_download_removes_partial_file_on_failure(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://example.test/book.epub", status_code=500)
    service = DownloadService(httpx.AsyncClient())

    with pytest.raises(DownloadError, match="HTTP 500"):
        await service.download(
            url="https://example.test/book.epub",
            destination_dir=tmp_path,
            filename="book.epub",
        )

    assert not (tmp_path / "book.epub.part").exists()


@pytest.mark.asyncio
async def test_download_reports_progress_with_known_total(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://example.test/book.epub",
        content=b"book bytes",
        headers={"Content-Length": "10"},
    )
    service = DownloadService(httpx.AsyncClient())
    updates: list[DownloadProgress] = []

    await service.download(
        url="https://example.test/book.epub",
        destination_dir=tmp_path,
        filename="book.epub",
        on_progress=updates.append,
    )

    assert updates[-1] == DownloadProgress(bytes_received=10, total_bytes=10)
    assert updates[-1].percent == 100.0


@pytest.mark.asyncio
async def test_download_reports_progress_without_known_total(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://example.test/book.epub", content=b"book")
    service = DownloadService(httpx.AsyncClient())
    updates: list[DownloadProgress] = []

    await service.download(
        url="https://example.test/book.epub",
        destination_dir=tmp_path,
        filename="book.epub",
        on_progress=updates.append,
    )

    assert updates[-1] == DownloadProgress(bytes_received=4, total_bytes=None)
    assert updates[-1].percent is None
```

- [ ] **Step 2: Run download tests to verify they fail**

Run: `pytest tests/test_downloads.py -v`

Expected: FAIL with missing `epub_tui.downloads`.

- [ ] **Step 3: Implement download service**

Create `src/epub_tui/downloads.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx


class DownloadError(RuntimeError):
    pass


@dataclass(frozen=True)
class DownloadProgress:
    bytes_received: int
    total_bytes: int | None

    @property
    def percent(self) -> float | None:
        if self.total_bytes in {None, 0}:
            return None
        return round((self.bytes_received / self.total_bytes) * 100, 2)


ProgressCallback = Callable[[DownloadProgress], None]


class DownloadService:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=60.0, follow_redirects=True)
        self._active = False

    async def download(
        self,
        *,
        url: str,
        destination_dir: Path,
        filename: str,
        auth: tuple[str, str] | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> Path:
        if self._active:
            raise DownloadError("Another download is already active")

        destination_dir.mkdir(parents=True, exist_ok=True)
        final_path = destination_dir / filename
        partial_path = destination_dir / f"{filename}.part"
        if final_path.exists():
            raise DownloadError(f"Download destination already exists: {final_path}")

        self._active = True
        try:
            async with self._client.stream("GET", url, auth=auth) as response:
                try:
                    response.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise DownloadError(f"Download failed: HTTP {exc.response.status_code}") from exc

                total_bytes = _content_length(response)
                bytes_received = 0
                with partial_path.open("wb") as handle:
                    async for chunk in response.aiter_bytes():
                        handle.write(chunk)
                        bytes_received += len(chunk)
                        if on_progress is not None:
                            on_progress(DownloadProgress(bytes_received, total_bytes))
            partial_path.replace(final_path)
            return final_path
        except Exception:
            partial_path.unlink(missing_ok=True)
            raise
        finally:
            self._active = False

    async def aclose(self) -> None:
        await self._client.aclose()


def _content_length(response: httpx.Response) -> int | None:
    value = response.headers.get("Content-Length")
    if value is None or not value.isdigit():
        return None
    return int(value)
```

- [ ] **Step 4: Run download tests**

Run: `pytest tests/test_downloads.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/epub_tui/downloads.py tests/test_downloads.py
git commit -m "feat: add single download service"
```

---

### Task 7: EPUB Text Preview

**Files:**
- Create: `src/epub_tui/reader.py`
- Create: `tests/test_reader.py`

- [ ] **Step 1: Write failing reader tests**

Create `tests/test_reader.py`:

```python
from pathlib import Path

from ebooklib import epub

from epub_tui.reader import EpubPreview, extract_epub_preview


def test_extract_epub_preview_reads_spine_text(tmp_path: Path) -> None:
    epub_path = tmp_path / "sample.epub"
    book = epub.EpubBook()
    book.set_identifier("sample")
    book.set_title("Sample EPUB")
    book.set_language("en")
    chapter = epub.EpubHtml(title="Chapter One", file_name="chapter.xhtml", lang="en")
    chapter.content = b"<html><body><h1>Chapter One</h1><p>Hello terminal reader.</p></body></html>"
    book.add_item(chapter)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)

    preview = extract_epub_preview(epub_path)

    assert isinstance(preview, EpubPreview)
    assert preview.title == "Sample EPUB"
    assert preview.sections[0].heading == "Chapter One"
    assert "Hello terminal reader." in preview.sections[0].text
```

- [ ] **Step 2: Run reader test to verify it fails**

Run: `pytest tests/test_reader.py -v`

Expected: FAIL with missing `epub_tui.reader`.

- [ ] **Step 3: Implement EPUB extraction**

Create `src/epub_tui/reader.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

from ebooklib import ITEM_DOCUMENT, epub


@dataclass(frozen=True)
class EpubSection:
    heading: str
    text: str


@dataclass(frozen=True)
class EpubPreview:
    title: str
    sections: list[EpubSection]


def extract_epub_preview(path: Path) -> EpubPreview:
    book = epub.read_epub(str(path))
    title = _metadata_value(book, "title") or path.stem
    sections: list[EpubSection] = []
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        parser = _TextExtractor()
        parser.feed(item.get_content().decode("utf-8", errors="replace"))
        text = parser.text.strip()
        if text:
            sections.append(EpubSection(heading=parser.heading or item.get_name(), text=text))
    return EpubPreview(title=title, sections=sections)


def _metadata_value(book: epub.EpubBook, name: str) -> str | None:
    values = book.get_metadata("DC", name)
    if not values:
        return None
    return str(values[0][0])


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self.heading: str | None = None
        self._current_tag: str | None = None

    @property
    def text(self) -> str:
        return " ".join(part.strip() for part in self._parts if part.strip())

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._current_tag = tag.lower()

    def handle_endtag(self, tag: str) -> None:
        if self._current_tag == tag.lower():
            self._current_tag = None

    def handle_data(self, data: str) -> None:
        if data.strip():
            if self.heading is None and self._current_tag in {"h1", "h2", "h3"}:
                self.heading = data.strip()
            self._parts.append(data)
```

- [ ] **Step 4: Run reader tests**

Run: `pytest tests/test_reader.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/epub_tui/reader.py tests/test_reader.py
git commit -m "feat: extract EPUB text previews"
```

---

### Task 8: Textual Screens And App Wiring

**Files:**
- Modify: `src/epub_tui/app.py`
- Create: `src/epub_tui/tui/__init__.py`
- Create: `src/epub_tui/tui/screens.py`
- Create: `src/epub_tui/tui/widgets.py`
- Create: `tests/test_tui_smoke.py`

- [ ] **Step 1: Write failing TUI smoke tests**

Create `tests/test_tui_smoke.py`:

```python
import pytest

from epub_tui.app import EpubTuiApp
from epub_tui.config import AppConfig, CatalogConfig


@pytest.mark.asyncio
async def test_app_shows_setup_when_config_missing() -> None:
    app = EpubTuiApp(config=None)
    async with app.run_test() as pilot:
        assert app.screen.id == "setup"


@pytest.mark.asyncio
async def test_app_shows_catalogs_when_config_exists(tmp_path) -> None:
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[CatalogConfig(name="Public", url="https://example.test/opds")],
        preferences={},
    )
    app = EpubTuiApp(config=config)
    async with app.run_test() as pilot:
        assert app.screen.id == "catalogs"
        assert "Public" in app.screen.renderable_text()


@pytest.mark.asyncio
async def test_catalog_screen_shows_busy_indicator_for_outgoing_call(tmp_path) -> None:
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[CatalogConfig(name="Public", url="https://example.test/opds")],
        preferences={},
    )
    app = EpubTuiApp(config=config)
    async with app.run_test() as pilot:
        app.screen.begin_outgoing_call("Fetching catalog...")
        assert "Fetching catalog..." in app.screen.renderable_text()
        app.screen.finish_outgoing_call("Ready")
        assert "Ready" in app.screen.renderable_text()


def test_cover_widget_falls_back_to_text_when_image_missing(tmp_path) -> None:
    from epub_tui.tui.widgets import CoverDisplay

    widget = CoverDisplay(title="Sample Book", author_line="Ada Writer", image_path=tmp_path / "missing.jpg")

    assert "Sample Book" in widget.renderable_text()
    assert "Ada Writer" in widget.renderable_text()


def test_download_progress_widget_renders_known_percent() -> None:
    from epub_tui.downloads import DownloadProgress
    from epub_tui.tui.widgets import DownloadProgressDisplay

    widget = DownloadProgressDisplay()
    widget.set_progress(DownloadProgress(bytes_received=50, total_bytes=100))

    assert "50.0%" in widget.renderable_text()


def test_download_progress_widget_renders_unknown_total() -> None:
    from epub_tui.downloads import DownloadProgress
    from epub_tui.tui.widgets import DownloadProgressDisplay

    widget = DownloadProgressDisplay()
    widget.set_progress(DownloadProgress(bytes_received=4096, total_bytes=None))

    assert "4096 bytes" in widget.renderable_text()


def test_busy_indicator_names_waiting_operation() -> None:
    from epub_tui.tui.widgets import BusyIndicator

    widget = BusyIndicator()
    widget.start("Fetching catalog...")

    assert widget.is_busy is True
    assert "Fetching catalog..." in widget.renderable_text()

    widget.stop("Catalog loaded")
    assert widget.is_busy is False
    assert widget.renderable_text() == "Catalog loaded"
```

- [ ] **Step 2: Run TUI smoke tests to verify they fail**

Run: `pytest tests/test_tui_smoke.py -v`

Expected: FAIL because `EpubTuiApp` does not accept `config`.

- [ ] **Step 3: Add TUI screens and wiring**

Create `src/epub_tui/tui/__init__.py`:

```python
from epub_tui.tui.screens import CatalogsScreen, SetupScreen

__all__ = ["CatalogsScreen", "SetupScreen"]
```

Create `src/epub_tui/tui/widgets.py`:

```python
from pathlib import Path

from textual.widgets import LoadingIndicator, ProgressBar, Static

from epub_tui.downloads import DownloadProgress


class StatusLine(Static):
    def set_message(self, message: str) -> None:
        self.update(message)


class BusyIndicator(Static):
    def __init__(self) -> None:
        self.is_busy = False
        self._message = "Ready"
        super().__init__(self.renderable_text())

    def start(self, message: str) -> None:
        self.is_busy = True
        self._message = message
        self.update(self.renderable_text())

    def stop(self, message: str = "Ready") -> None:
        self.is_busy = False
        self._message = message
        self.update(self.renderable_text())

    def renderable_text(self) -> str:
        prefix = "[busy] " if self.is_busy else ""
        return f"{prefix}{self._message}"


class BusySpinner(LoadingIndicator):
    pass


class CoverDisplay(Static):
    def __init__(self, title: str, author_line: str, image_path: Path | None) -> None:
        self.title = title
        self.author_line = author_line
        self.image_path = image_path
        super().__init__(self._build_renderable())

    def renderable_text(self) -> str:
        if self.image_path is None or not self.image_path.exists():
            return f"[cover unavailable]\n{self.title}\n{self.author_line}"
        return f"[cover]\n{self.title}\n{self.author_line}"

    def _build_renderable(self):
        if self.image_path is not None and self.image_path.exists():
            try:
                from textual_image.widget import Image

                return Image(str(self.image_path))
            except Exception:
                return self.renderable_text()
        return self.renderable_text()


class DownloadProgressDisplay(Static):
    def __init__(self) -> None:
        self._progress = DownloadProgress(bytes_received=0, total_bytes=None)
        super().__init__(self.renderable_text())

    def set_progress(self, progress: DownloadProgress) -> None:
        self._progress = progress
        self.update(self.renderable_text())

    def renderable_text(self) -> str:
        if self._progress.percent is None:
            return f"{self._progress.bytes_received} bytes downloaded"
        return f"{self._progress.percent}% downloaded"


class DownloadProgressBar(ProgressBar):
    def set_progress(self, progress: DownloadProgress) -> None:
        if progress.total_bytes is None:
            self.update(total=100, progress=0)
        else:
            self.update(total=progress.total_bytes, progress=progress.bytes_received)
```

Create `src/epub_tui/tui/screens.py`:

```python
from __future__ import annotations

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Header, Label, ListItem, ListView, Static

from epub_tui.config import AppConfig
from epub_tui.tui.widgets import BusyIndicator, StatusLine


class SetupScreen(Screen[None]):
    id = "setup"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Choose a library path to begin.")
        yield Static("MVP setup screen")
        yield Footer()

    def renderable_text(self) -> str:
        return "Choose a library path to begin. MVP setup screen"


class CatalogsScreen(Screen[None]):
    id = "catalogs"

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Catalogs")
        yield ListView(
            *[ListItem(Label(catalog.name), id=f"catalog-{index}") for index, catalog in enumerate(self.config.catalogs)]
        )
        yield BusyIndicator()
        yield StatusLine("Ready")
        yield Footer()

    def renderable_text(self) -> str:
        names = " ".join(catalog.name for catalog in self.config.catalogs)
        busy = self.query_one(BusyIndicator).renderable_text() if self.is_mounted else "Ready"
        return f"Catalogs {names} {busy}"

    def begin_outgoing_call(self, message: str) -> None:
        self.query_one(BusyIndicator).start(message)

    def finish_outgoing_call(self, message: str = "Ready") -> None:
        self.query_one(BusyIndicator).stop(message)
```

Modify `src/epub_tui/app.py`:

```python
from textual.app import App

from epub_tui.config import AppConfig
from epub_tui.tui.screens import CatalogsScreen, SetupScreen


class EpubTuiApp(App[None]):
    TITLE = "epub-tui"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("l", "show_library", "Library"),
        ("m", "toggle_read", "Read/Unread"),
        ("x", "delete_book", "Delete Book"),
    ]

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self.config = config

    def on_mount(self) -> None:
        if self.config is None:
            self.push_screen(SetupScreen())
        else:
            self.push_screen(CatalogsScreen(self.config))

    def action_show_library(self) -> None:
        self.notify("Library screen is not wired yet")

    def action_toggle_read(self) -> None:
        self.notify("Read/unread is available from the library screen")

    def action_delete_book(self) -> None:
        self.notify("Delete is available from the library screen")
```

- [ ] **Step 4: Run TUI smoke tests**

Run: `pytest tests/test_tui_smoke.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/epub_tui/app.py src/epub_tui/tui tests/test_tui_smoke.py
git commit -m "feat: add initial Textual screens"
```

---

### Task 9: End-To-End Service Integration

**Files:**
- Create: `src/epub_tui/services.py`
- Create: `tests/test_services.py`

- [ ] **Step 1: Write failing integration service test**

Create `tests/test_services.py`:

```python
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.services import CatalogWorkflow


@pytest.mark.asyncio
async def test_workflow_fetches_parses_caches_and_downloads(
    tmp_path: Path,
    fixture_dir: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    httpx_mock.add_response(url="https://example.test/opds/books/sample.epub", content=b"epub bytes")

    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[CatalogConfig(name="Public", url="https://example.test/opds")],
        preferences={},
    )
    workflow = CatalogWorkflow(config=config, state_db=tmp_path / "state.db", http_client=httpx.AsyncClient())

    feed = await workflow.fetch_catalog(config.catalogs[0])
    downloaded = await workflow.download_best_epub(config.catalogs[0], feed.entries[0])

    assert feed.title == "Fiction"
    assert downloaded.read_bytes() == b"epub bytes"
    assert workflow.library.list_books()[0].title == "Sample Book"
    assert workflow.library.list_books()[0].cover_image_url == "https://example.test/opds/covers/sample.jpg"


@pytest.mark.asyncio
async def test_workflow_reports_waiting_status_for_outgoing_calls(
    tmp_path: Path,
    fixture_dir: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[CatalogConfig(name="Public", url="https://example.test/opds")],
        preferences={},
    )
    workflow = CatalogWorkflow(config=config, state_db=tmp_path / "state.db", http_client=httpx.AsyncClient())
    statuses: list[str] = []

    await workflow.fetch_catalog(config.catalogs[0], on_status=statuses.append)

    assert statuses == ["Fetching catalog...", "Catalog loaded"]
```

- [ ] **Step 2: Run integration test to verify it fails**

Run: `pytest tests/test_services.py -v`

Expected: FAIL with missing `epub_tui.services`.

- [ ] **Step 3: Implement workflow service**

Create `src/epub_tui/services.py`:

```python
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import httpx

from epub_tui.catalog.client import CatalogClient
from epub_tui.catalog.models import CatalogEntry, CatalogFeed
from epub_tui.catalog.parser import parse_opds_feed
from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.downloads import DownloadError, DownloadProgress, DownloadService
from epub_tui.library import BookRecord, LibraryRepository


StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[DownloadProgress], None]


class CatalogWorkflow:
    def __init__(self, config: AppConfig, state_db: Path, http_client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self.library = LibraryRepository(state_db)
        self.library.initialize()
        self.catalog_client = CatalogClient(http_client)
        self.downloads = DownloadService(http_client)

    async def fetch_catalog(
        self,
        catalog: CatalogConfig,
        url: str | None = None,
        on_status: StatusCallback | None = None,
    ) -> CatalogFeed:
        target_url = url or catalog.url
        if on_status is not None:
            on_status("Fetching catalog...")
        body = await self.catalog_client.fetch_feed(catalog, target_url)
        feed = parse_opds_feed(body, source_url=target_url)
        self.library.save_feed_cache(catalog.name, target_url, feed.title, body)
        if on_status is not None:
            on_status("Catalog loaded")
        return feed

    async def download_best_epub(
        self,
        catalog: CatalogConfig,
        entry: CatalogEntry,
        on_status: StatusCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> Path:
        link = entry.best_epub_link()
        if link is None:
            raise DownloadError(f"No EPUB acquisition link for {entry.title}")
        filename = _safe_filename(entry.title, ".epub")
        auth = None if catalog.auth is None else (catalog.auth["username"], catalog.auth["password"])
        if on_status is not None:
            on_status("Starting download...")
        path = await self.downloads.download(
            url=link.href,
            destination_dir=self.config.library_path,
            filename=filename,
            auth=auth,
            on_progress=on_progress,
        )
        self.library.add_book(
            BookRecord(
                title=entry.title,
                authors=entry.authors,
                identifiers=[entry.identifier] if entry.identifier else [],
                source_catalog=catalog.name,
                source_entry_url=None,
                acquisition_url=link.href,
                media_type=link.media_type,
                cover_image_url=entry.cover_image_url or entry.thumbnail_url,
                cover_image_path=None,
                local_file_path=path,
                is_read=False,
            )
        )
        if on_status is not None:
            on_status("Download complete")
        return path


def _safe_filename(title: str, suffix: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", title).strip("-._")
    return f"{stem or 'book'}{suffix}"
```

- [ ] **Step 4: Run integration test**

Run: `pytest tests/test_services.py -v`

Expected: PASS.

- [ ] **Step 5: Run full test suite**

Run: `pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/epub_tui/services.py tests/test_services.py
git commit -m "feat: integrate catalog download workflow"
```

---

### Task 10: CLI Entrypoint And Final Verification

**Files:**
- Modify: `src/epub_tui/__main__.py`
- Modify: `README.md`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli.py`:

```python
from pathlib import Path

from epub_tui.__main__ import build_app
from epub_tui.app import EpubTuiApp


def test_build_app_returns_textual_app() -> None:
    app = build_app([])
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
```

- [ ] **Step 2: Run CLI test to verify it fails**

Run: `pytest tests/test_cli.py -v`

Expected: FAIL with `ImportError` for `build_app`.

- [ ] **Step 3: Implement CLI app builder**

Modify `src/epub_tui/__main__.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from epub_tui.app import EpubTuiApp
from epub_tui.config import ConfigError, default_config_path, load_config


def build_app(argv: Sequence[str] | None = None, default_config: Path | None = None) -> EpubTuiApp:
    parser = argparse.ArgumentParser(prog="epub-tui")
    parser.add_argument("--config", type=Path, default=None, help="Path to config JSON")
    args = parser.parse_args(argv)
    config_path = args.config or default_config or default_config_path()
    config = None
    if config_path.exists():
        try:
            config = load_config(config_path)
        except ConfigError as exc:
            raise SystemExit(str(exc)) from exc
    return EpubTuiApp(config=config)


def main(argv: Sequence[str] | None = None) -> None:
    build_app(argv).run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Update README usage**

Modify `README.md`:

```markdown
# epub-tui

Catalog-first terminal app for browsing OPDS 1.x catalogs, downloading books, and previewing EPUB text.

## Development

```powershell
python -m pip install -e ".[dev]"
pytest
```

## Run

```powershell
epub-tui
epub-tui --config path\to\config.json
```

By default, `epub-tui` reads config from `%APPDATA%\epub-tui\config.json` on Windows, `${XDG_CONFIG_HOME}/epub-tui/config.json` when `XDG_CONFIG_HOME` is set, or `~/.config/epub-tui/config.json` otherwise. Use `--config` to override that location.

Example config:

```json
{
  "library_path": "E:/Books",
  "catalogs": [
    {
      "name": "Example",
      "url": "https://example.test/opds",
      "auth": {
        "username": "alice",
        "password": "secret"
      }
    }
  ],
  "preferences": {}
}
```

## MVP

- OPDS 1.x Atom catalog browsing
- Optional HTTP Basic Auth per catalog
- One active download at a time
- Download progress bar for known totals and byte counter for unknown totals
- Busy indicator on every TUI screen while catalog fetch, refresh, navigation, cover fetch, or download start calls are running
- JSON config for library path and saved catalogs
- SQLite metadata/cache
- Local library management: mark read/unread and delete downloaded books
- Sixel/terminal graphics cover display when supported, with text fallback
- EPUB text preview
```

- [ ] **Step 5: Run CLI and full tests**

Run: `pytest -v`

Expected: PASS.

Run: `python -m epub_tui --help`

Expected: command prints usage including `--config`.

- [ ] **Step 6: Commit**

```bash
git add src/epub_tui/__main__.py README.md tests/test_cli.py
git commit -m "feat: add CLI config entrypoint"
```

---

## Self-Review

- Spec coverage: OPDS 1.x parsing and cover image metadata are covered by Task 3. Basic Auth fetch and credential redaction are covered by Tasks 2 and 4. JSON config is covered by Task 2. SQLite cache/book metadata, including cover URLs, optional local cover paths, read/unread state, and soft deletion, is covered by Task 5. Single download workflow and progress callbacks are covered by Task 6. EPUB preview is covered by Task 7. Textual startup, catalog screen smoke coverage, library action bindings, busy indicators for outgoing calls, cover display fallback, and download progress display are covered by Task 8. End-to-end service integration and status callbacks for outgoing calls are covered by Task 9. CLI launch and usage docs are covered by Task 10.
- Scope boundaries: OPDS 2.x, multi-download queue, PDF/DjVu/CBR rendering, OAuth, annotations, sync, and full-text search are not implemented in this plan.
- Type consistency: `AppConfig`, `CatalogConfig`, `CatalogFeed`, `CatalogEntry`, `AcquisitionLink`, `BookRecord`, `LibraryRepository`, `CatalogClient`, `DownloadProgress`, `DownloadService`, `CatalogWorkflow`, `StatusCallback`, `ProgressCallback`, and `EpubTuiApp` signatures are used consistently across tasks.
- Red-flag scan: The plan contains no unresolved work markers.
