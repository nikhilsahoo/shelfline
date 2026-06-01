# Shelfline 0.2.0 Reading Experience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Shelfline 0.2.0 as a cover-aware, more comfortable EPUB reading experience with persisted reader preferences and Zen Mode.

**Architecture:** Keep the existing layered package. Add typed preferences in `config`, cover caching in a new focused service module, per-book cover cache state in `library`, conservative image rendering in TUI detail panels, and reader comfort features in `reader`/`tui.reader` without replacing the existing EPUB reader flow.

**Tech Stack:** Python 3.11+, Textual/Rich, textual-image as optional/progressive rendering, httpx, ebooklib, SQLite, JSON config, pytest, pytest-asyncio, pytest-httpx.

---

## File Structure

- Create `src/shelfline/covers.py`: deterministic cover cache paths, OPDS cover fetch, EPUB embedded cover extraction.
- Modify `src/shelfline/config.py`: typed `ReaderPreferences`, `CoverPreferences`, `AppPreferences`; parse, validate, preserve, and serialize preference defaults.
- Modify `src/shelfline/library.py`: add `thumbnail_url` and `cover_cache_status` storage, plus update helpers for cached cover paths.
- Modify `src/shelfline/services.py`: opportunistically fetch/cache covers during download and expose a cover-cache helper for selected catalog/library entries.
- Modify `src/shelfline/tui/widgets.py`: upgrade `CoverDisplay` text fallback and add bounded optional `textual-image` render path.
- Modify `src/shelfline/tui/screens.py`: pass cover preferences into catalog/library detail panels and refresh cover state after downloads.
- Modify `src/shelfline/tui/reader.py`: reader preference classes, layout class switching, preference overlay, Zen Mode, bookmark navigator.
- Modify `src/shelfline/reader.py`: EPUB text cleanup improvements and embedded cover extraction support shared with `covers`.
- Modify `README.md`: document cover preferences, reader preferences, Zen Mode, and manual smoke updates.
- Add/extend tests:
  - `tests/test_config.py`
  - `tests/test_covers.py`
  - `tests/test_library.py`
  - `tests/test_services.py`
  - `tests/test_tui_smoke.py`
  - `tests/test_tui_flows.py`
  - `tests/test_reader.py`
  - `tests/test_reader_screen.py`

---

## Task 1: Typed Reader And Cover Preferences

**Files:**
- Modify: `src/shelfline/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing preference parsing tests**

Add to `tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_config.py::test_default_preferences_are_loaded_when_missing tests/test_config.py::test_reader_and_cover_preferences_round_trip tests/test_config.py::test_invalid_known_reader_preference_fails tests/test_config.py::test_invalid_known_cover_preference_fails -v
```

Expected: FAIL because `config.preferences` is still an untyped dictionary.

- [ ] **Step 3: Add preference dataclasses and parsing**

Modify `src/shelfline/config.py` by adding:

```python
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


@dataclass(frozen=True)
class AppPreferences:
    reader: ReaderPreferences = field(default_factory=ReaderPreferences)
    covers: CoverPreferences = field(default_factory=CoverPreferences)
    extra: dict[str, Any] = field(default_factory=dict)
```

Change `AppConfig.preferences` to:

```python
preferences: AppPreferences = field(default_factory=AppPreferences)
```

Add parser helpers:

```python
_READER_WIDTHS = {"narrow", "medium", "wide"}
_READER_THEMES = {"default", "warm", "high_contrast"}
_PARAGRAPH_SPACING = {"compact", "normal", "relaxed"}
_COVER_DISPLAY = {"auto", "text", "off"}


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
```

Update `_parse_config`:

```python
preferences = _parse_preferences(raw.get("preferences", {}))
```

Update JSON serialization:

```python
def _preferences_to_json(preferences: AppPreferences) -> dict[str, Any]:
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
    }
    return payload
```

Use `_preferences_to_json(config.preferences)` in `save_config` and
`redact_config`.

- [ ] **Step 4: Run preference tests**

Run:

```powershell
python -m pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit preferences**

```powershell
git add src/shelfline/config.py tests/test_config.py
git commit -m "feat: add reader and cover preferences"
```

---

## Task 2: Cover Cache Service

**Files:**
- Create: `src/shelfline/covers.py`
- Test: `tests/test_covers.py`

- [ ] **Step 1: Write failing cover cache tests**

Create `tests/test_covers.py`:

```python
from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from shelfline.covers import (
    CoverCache,
    CoverError,
    cached_cover_path,
    extract_epub_cover,
)


def test_cached_cover_path_is_deterministic_and_safe(tmp_path: Path) -> None:
    first = cached_cover_path(tmp_path, "https://example.test/covers/A Book.jpg")
    second = cached_cover_path(tmp_path, "https://example.test/covers/A Book.jpg")

    assert first == second
    assert first.parent == tmp_path / ".shelfline" / "covers"
    assert first.suffix == ".jpg"
    assert " " not in first.name


@pytest.mark.asyncio
async def test_cover_cache_fetches_public_cover(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://example.test/covers/book.jpg",
        content=b"image-bytes",
        headers={"content-type": "image/jpeg"},
    )
    cache = CoverCache(tmp_path, httpx.AsyncClient())

    path = await cache.fetch("https://example.test/covers/book.jpg")

    assert path.read_bytes() == b"image-bytes"
    assert path.suffix == ".jpg"


@pytest.mark.asyncio
async def test_cover_cache_uses_auth_for_same_origin_cover(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(200, content=b"cover", headers={"content-type": "image/jpeg"})

    httpx_mock.add_callback(handler, url="https://example.test/covers/private.jpg")
    cache = CoverCache(tmp_path, httpx.AsyncClient())

    path = await cache.fetch(
        "https://example.test/covers/private.jpg",
        auth=("reader", "secret"),
    )

    assert path.exists()


@pytest.mark.asyncio
async def test_cover_cache_failure_is_wrapped(tmp_path: Path, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://example.test/missing.jpg", status_code=404)
    cache = CoverCache(tmp_path, httpx.AsyncClient())

    with pytest.raises(CoverError, match="Could not fetch cover"):
        await cache.fetch("https://example.test/missing.jpg")


def test_extract_epub_cover_returns_none_without_cover(tmp_path: Path) -> None:
    epub_path = tmp_path / "empty.epub"
    epub_path.write_bytes(b"not an epub")

    assert extract_epub_cover(epub_path, tmp_path) is None
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_covers.py -v
```

Expected: FAIL because `shelfline.covers` does not exist.

- [ ] **Step 3: Implement `covers.py`**

Create `src/shelfline/covers.py`:

```python
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

import httpx
from ebooklib import ITEM_COVER, ITEM_IMAGE, epub


class CoverError(RuntimeError):
    """Raised when a remote cover cannot be cached."""


_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def cover_cache_dir(library_path: Path) -> Path:
    return Path(library_path) / ".shelfline" / "covers"


def cached_cover_path(library_path: Path, source_url: str, content_type: str | None = None) -> Path:
    extension = _extension_for_cover(source_url, content_type)
    digest = sha256(source_url.encode("utf-8")).hexdigest()[:24]
    return cover_cache_dir(library_path) / f"{digest}{extension}"


class CoverCache:
    def __init__(self, library_path: Path, http_client: httpx.AsyncClient) -> None:
        self.library_path = Path(library_path)
        self.http_client = http_client

    async def fetch(
        self,
        source_url: str,
        *,
        auth: tuple[str, str] | None = None,
    ) -> Path:
        try:
            response = await self.http_client.get(source_url, auth=auth)
            response.raise_for_status()
        except Exception as exc:
            raise CoverError(f"Could not fetch cover from {source_url}") from exc

        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        path = cached_cover_path(self.library_path, source_url, content_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return path


def extract_epub_cover(epub_path: Path, library_path: Path) -> Path | None:
    try:
        book = epub.read_epub(str(epub_path))
    except Exception:
        return None

    for item in book.get_items():
        if item.get_type() not in {ITEM_COVER, ITEM_IMAGE}:
            continue
        name = item.get_name().lower()
        if "cover" not in name and item.get_type() != ITEM_COVER:
            continue
        extension = Path(name).suffix.lower() or ".jpg"
        digest = sha256(f"{epub_path}:{name}".encode("utf-8")).hexdigest()[:24]
        path = cover_cache_dir(library_path) / f"{digest}{extension}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item.get_content())
        return path
    return None


def _extension_for_cover(source_url: str, content_type: str | None) -> str:
    if content_type:
        extension = _CONTENT_TYPE_EXTENSIONS.get(content_type.lower())
        if extension is not None:
            return extension
    suffix = Path(urlparse(source_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"
```

- [ ] **Step 4: Run cover tests**

Run:

```powershell
python -m pytest tests/test_covers.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit cover cache service**

```powershell
git add src/shelfline/covers.py tests/test_covers.py
git commit -m "feat: add cover cache service"
```

---

## Task 3: Library Cover Metadata Migration

**Files:**
- Modify: `src/shelfline/library.py`
- Test: `tests/test_library.py`

- [ ] **Step 1: Write failing metadata tests**

Add to `tests/test_library.py`:

```python
def test_book_record_stores_thumbnail_and_cover_cache_status(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    cover_path = tmp_path / ".shelfline" / "covers" / "cover.jpg"
    book = _book_record(
        tmp_path,
        cover_image_url="https://example.test/full.jpg",
        cover_image_path=cover_path,
    )
    book = replace(
        book,
        thumbnail_url="https://example.test/thumb.jpg",
        cover_cache_status="cached",
    )

    repo.add_book(book)

    [stored] = repo.list_books()
    assert stored.thumbnail_url == "https://example.test/thumb.jpg"
    assert stored.cover_cache_status == "cached"
    assert stored.cover_image_path == cover_path


def test_update_book_cover_cache_path(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book = _book_record(tmp_path, cover_image_url="https://example.test/full.jpg")
    repo.add_book(book)
    cover_path = tmp_path / ".shelfline" / "covers" / "cover.jpg"

    repo.update_cover_cache(book.local_file_path, cover_path, status="cached")

    [stored] = repo.list_books()
    assert stored.cover_image_path == cover_path
    assert stored.cover_cache_status == "cached"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_library.py::test_book_record_stores_thumbnail_and_cover_cache_status tests/test_library.py::test_update_book_cover_cache_path -v
```

Expected: FAIL because `BookRecord` has no `thumbnail_url` or
`cover_cache_status`.

- [ ] **Step 3: Extend `BookRecord` and schema**

Modify `src/shelfline/library.py`:

```python
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
    thumbnail_url: str | None = None
    cover_cache_status: str | None = None
    is_read: bool = False
    deleted_at: str | None = None
```

After `CREATE TABLE books`, add compatibility migrations:

```python
self._ensure_column(connection, "books", "thumbnail_url", "TEXT")
self._ensure_column(connection, "books", "cover_cache_status", "TEXT")
```

Add helper:

```python
def _ensure_column(
    self,
    connection: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
```

Update `INSERT`, `SELECT`, and `_book_from_row` to include
`thumbnail_url` and `cover_cache_status`.

Add:

```python
def update_cover_cache(
    self,
    local_file_path: Path,
    cover_image_path: Path | None,
    *,
    status: str | None,
) -> None:
    with self._connect() as connection:
        connection.execute(
            """
            UPDATE books
            SET cover_image_path = ?, cover_cache_status = ?
            WHERE local_file_path = ?
            """,
            (
                self._path_to_text(cover_image_path),
                status,
                self._path_to_text(local_file_path),
            ),
        )
```

- [ ] **Step 4: Run library tests**

Run:

```powershell
python -m pytest tests/test_library.py tests/test_library_search.py tests/test_reading_progress.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit library cover metadata**

```powershell
git add src/shelfline/library.py tests/test_library.py
git commit -m "feat: store cover cache metadata"
```

---

## Task 4: Cover Caching In Catalog Workflow

**Files:**
- Modify: `src/shelfline/services.py`
- Test: `tests/test_services.py`

- [ ] **Step 1: Write failing workflow tests**

Add to `tests/test_services.py`:

```python
async def test_download_caches_entry_cover_when_available(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    httpx_mock.add_response(url="https://example.test/opds/books/sample.epub", content=b"epub")
    httpx_mock.add_response(
        url="https://example.test/opds/covers/sample.jpg",
        content=b"cover",
        headers={"content-type": "image/jpeg"},
    )
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books"),
        state_db=tmp_path / "state.db",
        http_client=httpx.AsyncClient(),
    )

    feed = await workflow.fetch_catalog(CatalogConfig(name="Example", url="https://example.test/opds"))
    await workflow.download_acquisition(
        CatalogConfig(name="Example", url="https://example.test/opds"),
        feed.entries[0],
    )

    [book] = workflow.library.list_books()
    assert book.cover_image_path is not None
    assert book.cover_image_path.exists()
    assert book.cover_cache_status == "cached"


async def test_download_succeeds_when_cover_fetch_fails(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    httpx_mock.add_response(url="https://example.test/opds/books/sample.epub", content=b"epub")
    httpx_mock.add_response(url="https://example.test/opds/covers/sample.jpg", status_code=500)
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books"),
        state_db=tmp_path / "state.db",
        http_client=httpx.AsyncClient(),
    )

    feed = await workflow.fetch_catalog(CatalogConfig(name="Example", url="https://example.test/opds"))
    path = await workflow.download_acquisition(
        CatalogConfig(name="Example", url="https://example.test/opds"),
        feed.entries[0],
    )

    [book] = workflow.library.list_books()
    assert path.exists()
    assert book.cover_image_path is None
    assert book.cover_cache_status == "error"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_services.py::test_download_caches_entry_cover_when_available tests/test_services.py::test_download_succeeds_when_cover_fetch_fails -v
```

Expected: FAIL because downloads do not cache covers.

- [ ] **Step 3: Integrate `CoverCache` into workflow**

Modify `src/shelfline/services.py`:

```python
from shelfline.covers import CoverCache, CoverError, extract_epub_cover
```

In `CatalogWorkflow.__init__`:

```python
self._cover_cache = CoverCache(config.library_path, self._http_client)
```

Add:

```python
async def _cache_cover_for_book(
    self,
    catalog: CatalogConfig,
    entry: CatalogEntry,
    downloaded_path: Path,
) -> tuple[Path | None, str | None]:
    cover_url = entry.cover_image_url or entry.thumbnail_url
    if cover_url is not None:
        try:
            auth = _auth_tuple(catalog, self._credentials) if _same_origin(catalog.url, cover_url) else None
            return await self._cover_cache.fetch(cover_url, auth=auth), "cached"
        except CoverError:
            return None, "error"

    embedded = extract_epub_cover(downloaded_path, self.config.library_path)
    if embedded is not None:
        return embedded, "cached"
    return None, None
```

In `download_acquisition`, after the file download:

```python
cover_path, cover_status = await self._cache_cover_for_book(catalog, entry, downloaded_path)
```

Use these in `BookRecord`, and store `thumbnail_url=entry.thumbnail_url`.

- [ ] **Step 4: Run service tests**

Run:

```powershell
python -m pytest tests/test_services.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit workflow cover caching**

```powershell
git add src/shelfline/services.py tests/test_services.py
git commit -m "feat: cache covers during downloads"
```

---

## Task 5: Polished Cover Display Widget

**Files:**
- Modify: `src/shelfline/tui/widgets.py`
- Test: `tests/test_tui_smoke.py`

- [ ] **Step 1: Write failing cover display tests**

Add to `tests/test_tui_smoke.py`:

```python
def test_cover_display_text_mode_shows_polished_metadata() -> None:
    display = CoverDisplay(
        title="Dune",
        authors=["Frank Herbert"],
        image_path=None,
        media_type="application/epub+zip",
        source="Calibre-Web",
        display_mode="text",
        cache_status=None,
    )

    rendered = str(display.renderable)
    assert "Dune" in rendered
    assert "Frank Herbert" in rendered
    assert "application/epub+zip" in rendered
    assert "Calibre-Web" in rendered
    assert "Cover unavailable" in rendered


def test_cover_display_off_mode_hides_cover_block() -> None:
    display = CoverDisplay(
        title="Dune",
        authors=["Frank Herbert"],
        display_mode="off",
    )

    assert str(display.renderable) == ""
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_tui_smoke.py::test_cover_display_text_mode_shows_polished_metadata tests/test_tui_smoke.py::test_cover_display_off_mode_hides_cover_block -v
```

Expected: FAIL because `CoverDisplay` does not accept the new arguments.

- [ ] **Step 3: Upgrade `CoverDisplay`**

Modify `CoverDisplay.__init__` in `src/shelfline/tui/widgets.py`:

```python
def __init__(
    self,
    *,
    title: str,
    authors: list[str] | tuple[str, ...] | None = None,
    image_path: str | Path | None = None,
    terminal_graphics: bool = False,
    display_mode: str = "auto",
    media_type: str | None = None,
    source: str | None = None,
    cache_status: str | None = None,
    **kwargs: object,
) -> None:
    self.title = title
    self.authors = list(authors or [])
    self.image_path = Path(image_path) if image_path is not None else None
    self.terminal_graphics = terminal_graphics
    self.display_mode = display_mode
    self.media_type = media_type
    self.source = source
    self.cache_status = cache_status
    renderable = self._render_cover()
    super().__init__(renderable, **kwargs)
    self._renderable = renderable
```

Replace `_render_cover`:

```python
def _render_cover(self) -> str:
    if self.display_mode == "off":
        return ""
    author_text = ", ".join(self.authors) if self.authors else "Unknown author"
    status = self._cover_status()
    lines = [self.title, author_text]
    if self.media_type:
        lines.append(self.media_type)
    if self.source:
        lines.append(self.source)
    lines.append(status)
    return "\n".join(lines)


def _cover_status(self) -> str:
    if self.cache_status == "cached" and self.image_path is not None:
        return "Cover cached"
    if self.cache_status == "error":
        return "Cover unavailable"
    if self.image_path is not None and self.image_path.exists():
        return "Cover cached"
    return "Cover unavailable"
```

- [ ] **Step 4: Run smoke tests**

Run:

```powershell
python -m pytest tests/test_tui_smoke.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit cover fallback polish**

```powershell
git add src/shelfline/tui/widgets.py tests/test_tui_smoke.py
git commit -m "feat: polish cover fallback display"
```

---

## Task 6: Cover-Aware Detail Panels

**Files:**
- Modify: `src/shelfline/tui/screens.py`
- Test: `tests/test_tui_flows.py`

- [ ] **Step 1: Write failing detail panel tests**

Add to `tests/test_tui_flows.py`:

```python
async def test_library_detail_uses_cover_preferences(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(
        BookRecord(
            title="Dune",
            authors=["Frank Herbert"],
            identifiers=["urn:dune"],
            source_catalog="Calibre-Web",
            source_entry_url=None,
            acquisition_url="https://example.test/dune.epub",
            media_type="application/epub+zip",
            cover_image_url="https://example.test/dune.jpg",
            thumbnail_url="https://example.test/dune-thumb.jpg",
            cover_image_path=None,
            cover_cache_status=None,
            local_file_path=tmp_path / "Dune.epub",
            is_read=False,
        )
    )
    config = AppConfig(
        library_path=tmp_path,
        preferences=AppPreferences(covers=CoverPreferences(display="text")),
    )
    app = ShelflineApp(config=config, library=repo)

    async with app.run_test():
        app.action_show_library()
        rendered = str(app.screen.query_one("#detail-region").render())
        assert "Dune" in rendered
        assert "Cover unavailable" in rendered
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_tui_flows.py::test_library_detail_uses_cover_preferences -v
```

Expected: FAIL because detail panels do not pass cover preferences/metadata.

- [ ] **Step 3: Pass preferences into `CoverDisplay`**

Modify `LibraryScreen` and catalog entry/detail rendering in
`src/shelfline/tui/screens.py`:

```python
cover_preferences = self.app.config.preferences.covers if self.app.config is not None else CoverPreferences()
display = CoverDisplay(
    title=book.title,
    authors=book.authors,
    image_path=book.cover_image_path,
    display_mode=cover_preferences.display,
    media_type=book.media_type,
    source=book.source_catalog,
    cache_status=book.cover_cache_status,
    id="cover-display",
)
```

For catalog entries that are not downloaded yet:

```python
CoverDisplay(
    title=self.entry.title,
    authors=self.entry.authors,
    image_path=None,
    display_mode=cover_preferences.display,
    media_type=self._selected_acquisition_media_type(),
    source=self.catalog.name,
    cache_status=None,
    id="cover-display",
)
```

- [ ] **Step 4: Run TUI flow tests**

Run:

```powershell
python -m pytest tests/test_tui_flows.py tests/test_tui_smoke.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit cover-aware details**

```powershell
git add src/shelfline/tui/screens.py tests/test_tui_flows.py
git commit -m "feat: show cover-aware detail panels"
```

---

## Task 7: Optional Terminal Image Rendering

**Files:**
- Modify: `src/shelfline/tui/widgets.py`
- Test: `tests/test_tui_smoke.py`

- [ ] **Step 1: Write failing terminal image fallback tests**

Add to `tests/test_tui_smoke.py`:

```python
def test_cover_display_auto_mode_does_not_expose_image_path_when_rendering_fails(tmp_path: Path) -> None:
    image = tmp_path / "cover.jpg"
    image.write_bytes(b"not-a-real-image")
    display = CoverDisplay(
        title="Dune",
        authors=["Frank Herbert"],
        image_path=image,
        terminal_graphics=True,
        display_mode="auto",
        cache_status="cached",
    )

    rendered = str(display.renderable)
    assert "Dune" in rendered
    assert str(image) not in rendered
```

- [ ] **Step 2: Run test to verify current fallback**

Run:

```powershell
python -m pytest tests/test_tui_smoke.py::test_cover_display_auto_mode_does_not_expose_image_path_when_rendering_fails -v
```

Expected: PASS if the current fallback already avoids raw paths; keep this as a regression test.

- [ ] **Step 3: Add optional image widget composition**

Modify `CoverDisplay.compose` in `src/shelfline/tui/widgets.py`:

```python
def compose(self) -> ComposeResult:
    image_widget = self._image_widget()
    if image_widget is not None:
        yield image_widget
    yield Static(self._render_cover(), classes="cover-fallback")


def _image_widget(self) -> Widget | None:
    if self.display_mode != "auto" or not self.terminal_graphics:
        return None
    if self.image_path is None or not self.image_path.exists():
        return None
    try:
        from textual_image.widget import Image
    except Exception:
        return None
    try:
        return Image(str(self.image_path), classes="cover-image")
    except Exception:
        return None
```

Import `ComposeResult`, `Widget`, and `Static` if not already available in the
file.

- [ ] **Step 4: Run widget tests**

Run:

```powershell
python -m pytest tests/test_tui_smoke.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit optional image rendering**

```powershell
git add src/shelfline/tui/widgets.py tests/test_tui_smoke.py
git commit -m "feat: add optional terminal cover rendering"
```

---

## Task 8: Reader Preference Layout Classes

**Files:**
- Modify: `src/shelfline/tui/reader.py`
- Modify: `src/shelfline/tui/app.tcss`
- Test: `tests/test_reader_screen.py`

- [ ] **Step 1: Write failing reader preference tests**

Add to `tests/test_reader_screen.py`:

```python
async def test_reader_screen_applies_reader_preference_classes() -> None:
    preview = _preview(title="Reader Title")
    preferences = ReaderPreferences(
        width="wide",
        theme="warm",
        paragraph_spacing="relaxed",
        show_progress=False,
        show_chapter_title=False,
    )
    app = ShelflineApp(config=AppConfig(library_path=Path(".")))

    async with app.run_test():
        await app.push_screen(EpubReaderScreen(preview, preferences=preferences))
        page = app.screen.query_one("#reader-page")
        assert page.has_class("reader-width-wide")
        assert page.has_class("reader-theme-warm")
        assert page.has_class("reader-spacing-relaxed")
        assert app.screen.query_one("#reader-progress").display is False
        assert app.screen.query_one("#reader-heading").display is False
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_reader_screen.py::test_reader_screen_applies_reader_preference_classes -v
```

Expected: FAIL because `EpubReaderScreen` has no `preferences` argument.

- [ ] **Step 3: Apply preference classes**

Modify `src/shelfline/tui/reader.py`:

```python
from shelfline.config import ReaderPreferences
```

Update `EpubReaderScreen.__init__`:

```python
preferences: ReaderPreferences | None = None,
```

Set:

```python
self.preferences = preferences or ReaderPreferences()
```

In `compose`, set page classes:

```python
classes=(
    "reader-page "
    f"reader-width-{self.preferences.width} "
    f"reader-theme-{self.preferences.theme} "
    f"reader-spacing-{self.preferences.paragraph_spacing}"
)
```

After yielding heading/progress:

```python
heading = StatusLine(section.heading, id="reader-heading", classes="reader-heading")
heading.display = self.preferences.show_chapter_title
yield heading
```

In `ReaderChrome.compose` or after mount:

```python
progress = StatusLine(self.progress, id="reader-progress", classes="reader-progress")
progress.display = self.show_progress
yield progress
```

Pass `show_progress=self.preferences.show_progress` into `ReaderChrome`.

Add CSS classes to `src/shelfline/tui/app.tcss`:

```css
.reader-width-narrow {
    max-width: 72;
}

.reader-width-medium {
    max-width: 92;
}

.reader-width-wide {
    max-width: 118;
}

.reader-spacing-compact .reader-text {
    padding-top: 0;
}

.reader-spacing-normal .reader-text {
    padding-top: 1;
}

.reader-spacing-relaxed .reader-text {
    padding-top: 2;
}

.reader-theme-warm {
    color: #eadfc9;
}

.reader-theme-high_contrast {
    color: white;
    background: black;
}
```

- [ ] **Step 4: Run reader screen tests**

Run:

```powershell
python -m pytest tests/test_reader_screen.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit reader preference layout**

```powershell
git add src/shelfline/tui/reader.py src/shelfline/tui/app.tcss tests/test_reader_screen.py
git commit -m "feat: apply reader layout preferences"
```

---

## Task 9: Reader Preference Overlay And Persistence

**Files:**
- Modify: `src/shelfline/tui/reader.py`
- Modify: `src/shelfline/tui/screens.py`
- Modify: `src/shelfline/config.py`
- Test: `tests/test_reader_screen.py`

- [ ] **Step 1: Write failing preference overlay test**

Add to `tests/test_reader_screen.py`:

```python
async def test_reader_preferences_overlay_changes_width_and_saves(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    config = AppConfig(library_path=tmp_path)
    app = ShelflineApp(config=config, config_path=config_path)

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview(), preferences=config.preferences.reader))
        await pilot.press("o")
        await pilot.press("w")

        assert app.screen.preferences.width == "wide"
        saved = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved["preferences"]["reader"]["width"] == "wide"
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_reader_screen.py::test_reader_preferences_overlay_changes_width_and_saves -v
```

Expected: FAIL because there is no preferences overlay or save path.

- [ ] **Step 3: Add config save hook to app if needed**

If `ShelflineApp` does not already hold `config_path`, modify `src/shelfline/app.py`:

```python
def __init__(
    self,
    config: AppConfig | None = None,
    *,
    config_path: Path | None = None,
    ...
) -> None:
    super().__init__()
    self.config = config
    self.config_path = config_path
```

Add:

```python
def save_config(self) -> None:
    if self.config is None or self.config_path is None:
        return
    save_config(self.config_path, self.config)
```

- [ ] **Step 4: Add reader preference mutation**

In `src/shelfline/tui/reader.py`, add binding:

```python
("o", "reader_options", "Options"),
```

Implement a compact screen `ReaderPreferencesScreen` with bindings:

```python
BINDINGS = [
    ("n", "set_width_narrow", "Narrow"),
    ("m", "set_width_medium", "Medium"),
    ("w", "set_width_wide", "Wide"),
    ("b", "dismiss", "Back"),
]
```

Each action calls:

```python
self.reader.update_preferences(replace(self.reader.preferences, width="wide"))
self.app.pop_screen()
```

Implement `EpubReaderScreen.update_preferences`:

```python
def update_preferences(self, preferences: ReaderPreferences) -> None:
    self.preferences = preferences
    if self.app.config is not None:
        self.app.config = replace(
            self.app.config,
            preferences=replace(self.app.config.preferences, reader=preferences),
        )
        try:
            self.app.save_config()
        except Exception as error:
            self._set_status(f"Preferences not saved: {error}")
    self._apply_preference_classes()
```

Implement `_apply_preference_classes` to remove old `reader-width-*`,
`reader-theme-*`, and `reader-spacing-*` classes and add the new ones.

- [ ] **Step 5: Run focused test**

Run:

```powershell
python -m pytest tests/test_reader_screen.py::test_reader_preferences_overlay_changes_width_and_saves -v
```

Expected: PASS.

- [ ] **Step 6: Run reader tests**

Run:

```powershell
python -m pytest tests/test_reader_screen.py tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit reader preference controls**

```powershell
git add src/shelfline/app.py src/shelfline/config.py src/shelfline/tui/reader.py tests/test_reader_screen.py
git commit -m "feat: add reader preference controls"
```

---

## Task 10: Reader Zen Mode

**Files:**
- Modify: `src/shelfline/tui/reader.py`
- Modify: `src/shelfline/tui/app.tcss`
- Test: `tests/test_reader_screen.py`

- [ ] **Step 1: Write failing Zen Mode tests**

Add to `tests/test_reader_screen.py`:

```python
async def test_reader_zen_mode_hides_nonessential_chrome_and_preserves_scroll() -> None:
    app = ShelflineApp(config=AppConfig(library_path=Path(".")))

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview_with_long_text()))
        reader_body = app.screen.query_one("#reader-body", VerticalScroll)
        await _scroll_reader_body(reader_body, y=20, pilot=pilot)
        before = reader_body.scroll_y
        await pilot.press("z")

        assert app.screen.has_class("zen-mode")
        assert app.screen.query_one("#key-hints").display is False
        assert app.screen.query_one("#status-line").display is False
        assert reader_body.scroll_y == before

        await pilot.press("z")
        assert not app.screen.has_class("zen-mode")
        assert app.screen.query_one("#key-hints").display is True
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_reader_screen.py::test_reader_zen_mode_hides_nonessential_chrome_and_preserves_scroll -v
```

Expected: FAIL because `z` is unbound.

- [ ] **Step 3: Implement Zen Mode toggle**

In `EpubReaderScreen.BINDINGS`, add:

```python
("z", "toggle_zen", "Zen"),
```

Set initial state:

```python
self.zen_mode = self.preferences.zen_mode_default
```

In `on_mount`, call:

```python
self._apply_zen_mode()
```

Add:

```python
def action_toggle_zen(self) -> None:
    self.zen_mode = not self.zen_mode
    self._apply_zen_mode()


def _apply_zen_mode(self) -> None:
    self.set_class(self.zen_mode, "zen-mode")
    self.query_one("#key-hints", KeyHintFooter).display = not self.zen_mode
    self.query_one("#status-line", StatusLine).display = not self.zen_mode
```

Add CSS:

```css
.zen-mode #reader-page {
    border: none;
}

.zen-mode #reader-surface {
    padding: 0 2;
}
```

- [ ] **Step 4: Run Zen Mode tests**

Run:

```powershell
python -m pytest tests/test_reader_screen.py::test_reader_zen_mode_hides_nonessential_chrome_and_preserves_scroll -v
```

Expected: PASS.

- [ ] **Step 5: Run reader test suite**

Run:

```powershell
python -m pytest tests/test_reader_screen.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit Zen Mode**

```powershell
git add src/shelfline/tui/reader.py src/shelfline/tui/app.tcss tests/test_reader_screen.py
git commit -m "feat: add reader zen mode"
```

---

## Task 11: Bookmark Navigator

**Files:**
- Modify: `src/shelfline/tui/reader.py`
- Test: `tests/test_reader_screen.py`

- [ ] **Step 1: Write failing bookmark navigator test**

Add to `tests/test_reader_screen.py`:

```python
async def test_reader_bookmark_navigator_opens_and_jumps(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "book.epub"
    repo.add_bookmark(
        Bookmark(
            local_file_path=book_path,
            section_index=1,
            position=0,
            label="Chapter Two",
        )
    )
    app = ShelflineApp(config=AppConfig(library_path=tmp_path))

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview(), library=repo, book_path=book_path))
        await pilot.press("g")
        assert "Chapter Two" in str(app.screen.query_one("#bookmark-list").render())
        await pilot.press("enter")
        reader = app.screen
        assert isinstance(reader, EpubReaderScreen)
        assert reader.section_index == 1
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_reader_screen.py::test_reader_bookmark_navigator_opens_and_jumps -v
```

Expected: FAIL because there is no bookmark navigator.

- [ ] **Step 3: Add bookmark navigator screen**

In `src/shelfline/tui/reader.py`, add binding:

```python
("g", "bookmark_navigator", "Bookmarks"),
```

Implement:

```python
class ReaderBookmarkScreen(Screen[None]):
    BINDINGS = [
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("enter", "jump_to_bookmark", "Jump"),
        ("b", "dismiss", "Back"),
    ]

    def __init__(self, reader: EpubReaderScreen) -> None:
        super().__init__()
        self.reader = reader
        self.bookmarks = (
            reader.library.list_bookmarks(reader.book_path)
            if reader.library is not None and reader.book_path is not None
            else []
        )
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(self._bookmark_text(), id="bookmark-list")
        yield KeyHintFooter("Keys: j down | k up | enter jump | b back")

    def action_cursor_down(self) -> None:
        if self.bookmarks:
            self.selected_index = min(self.selected_index + 1, len(self.bookmarks) - 1)
            self.query_one("#bookmark-list", Static).update(self._bookmark_text())

    def action_cursor_up(self) -> None:
        if self.bookmarks:
            self.selected_index = max(self.selected_index - 1, 0)
            self.query_one("#bookmark-list", Static).update(self._bookmark_text())

    def action_jump_to_bookmark(self) -> None:
        if self.bookmarks:
            self.reader.jump_to_section(self.bookmarks[self.selected_index].section_index)
        self.app.pop_screen()

    def action_dismiss(self) -> None:
        self.app.pop_screen()

    def _bookmark_text(self) -> str:
        if not self.bookmarks:
            return "No bookmarks"
        lines = []
        for index, bookmark in enumerate(self.bookmarks):
            marker = ">" if index == self.selected_index else " "
            lines.append(f"{marker} {bookmark.label}")
        return "\n".join(lines)
```

Add `EpubReaderScreen.action_bookmark_navigator`:

```python
def action_bookmark_navigator(self) -> None:
    self.app.push_screen(ReaderBookmarkScreen(self))
```

- [ ] **Step 4: Run bookmark navigator tests**

Run:

```powershell
python -m pytest tests/test_reader_screen.py::test_reader_bookmark_navigator_opens_and_jumps -v
```

Expected: PASS.

- [ ] **Step 5: Run reader tests**

Run:

```powershell
python -m pytest tests/test_reader_screen.py tests/test_reading_progress.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit bookmark navigator**

```powershell
git add src/shelfline/tui/reader.py tests/test_reader_screen.py
git commit -m "feat: add reader bookmark navigator"
```

---

## Task 12: TOC Polish

**Files:**
- Modify: `src/shelfline/tui/reader.py`
- Test: `tests/test_reader_screen.py`

- [ ] **Step 1: Write failing TOC display test**

Add to `tests/test_reader_screen.py`:

```python
async def test_reader_toc_marks_current_section_and_progress() -> None:
    app = ShelflineApp(config=AppConfig(library_path=Path(".")))

    async with app.run_test() as pilot:
        await app.push_screen(EpubReaderScreen(_preview(), section_index=1))
        await pilot.press("t")
        rendered = str(app.screen.query_one("#toc-list").render())
        assert "current" in rendered.lower()
        assert "2 / 2" in rendered
```

- [ ] **Step 2: Run test to verify failure**

Run:

```powershell
python -m pytest tests/test_reader_screen.py::test_reader_toc_marks_current_section_and_progress -v
```

Expected: FAIL because TOC rows only show title.

- [ ] **Step 3: Improve TOC row text**

Update `ReaderTocList` so it accepts `current_section_index`:

```python
def __init__(..., current_section_index: int = 0, section_count: int = 0, **kwargs: object) -> None:
    ...
    self.current_section_index = current_section_index
    self.section_count = section_count
```

Update `_row_text`:

```python
def _row_text(self, entry: EpubOutlineItem, index: int) -> str:
    prefix = ">" if index == self.selected_index else " "
    current = " current" if entry.section_index == self.current_section_index else ""
    progress = f"{entry.section_index + 1} / {self.section_count}"
    return f"{prefix} {entry.title}  {progress}{current}"
```

Pass current values from `ReaderTocScreen.compose`.

- [ ] **Step 4: Run TOC tests**

Run:

```powershell
python -m pytest tests/test_reader_screen.py::test_reader_toc_marks_current_section_and_progress tests/test_reader_screen.py::test_reader_toc_scrolls_to_keep_long_outline_selection_visible -v
```

Expected: PASS.

- [ ] **Step 5: Commit TOC polish**

```powershell
git add src/shelfline/tui/reader.py tests/test_reader_screen.py
git commit -m "feat: polish reader table of contents"
```

---

## Task 13: EPUB Text Cleanup Improvements

**Files:**
- Modify: `src/shelfline/reader.py`
- Test: `tests/test_reader.py`

- [ ] **Step 1: Write failing text cleanup tests**

Add to `tests/test_reader.py`:

```python
def test_reader_cleanup_removes_leftover_break_tags_and_entities(tmp_path: Path) -> None:
    epub_path = tmp_path / "cleanup.epub"
    _write_epub(
        epub_path,
        [
            (
                "chapter.xhtml",
                b"<html><body><h1>Chapter</h1><p>One&lt;br /&gt;Two&nbsp;&amp; Three</p></body></html>",
            )
        ],
    )

    preview = extract_epub_preview(epub_path)

    assert "<br" not in preview.sections[0].text
    assert "One" in preview.sections[0].text
    assert "Two & Three" in preview.sections[0].text


def test_reader_skips_titlepage_like_structural_sections(tmp_path: Path) -> None:
    epub_path = tmp_path / "structural.epub"
    _write_epub(
        epub_path,
        [
            ("titlepage.xhtml", b"<html><body><h1>Cover</h1></body></html>"),
            ("chapter.xhtml", b"<html><body><h1>Real Chapter</h1><p>Readable.</p></body></html>"),
        ],
    )

    preview = extract_epub_preview(epub_path)

    assert [section.heading for section in preview.sections] == ["Real Chapter"]
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_reader.py::test_reader_cleanup_removes_leftover_break_tags_and_entities tests/test_reader.py::test_reader_skips_titlepage_like_structural_sections -v
```

Expected: FAIL for at least the new cleanup/structural cases.

- [ ] **Step 3: Improve cleanup**

Modify `src/shelfline/reader.py`:

```python
import html
```

Update `_normalize_block_text`:

```python
def _normalize_block_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"(?i)<br\s*/?>", "\n", value)
    value = re.sub(r"(?i)</p\s*>", "\n\n", value)
    value = re.sub(r"(?i)<[^>]+>", "", value)
    lines = [_normalize_inline_text(line) for line in value.splitlines()]
    blocks: list[str] = []
    for line in lines:
        if line:
            blocks.append(line)
        elif blocks and blocks[-1] != "":
            blocks.append("")
    return "\n".join(blocks).strip()
```

Extend structural tokens:

```python
_STRUCTURAL_LABEL_TOKENS.update({"cover", "titlepage", "title-page", "copyright"})
_STRUCTURAL_LABEL_PHRASES = ("table of contents", "title page")
```

Ensure `_is_structural_document_item` checks both item name and heading tokens.

- [ ] **Step 4: Run reader tests**

Run:

```powershell
python -m pytest tests/test_reader.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit EPUB cleanup**

```powershell
git add src/shelfline/reader.py tests/test_reader.py
git commit -m "feat: improve epub text cleanup"
```

---

## Task 14: Documentation And Screenshots

**Files:**
- Modify: `README.md`
- Modify: `docs/assets/screenshots/README.md`

- [ ] **Step 1: Update README feature docs**

Add to `README.md` under usage:

```markdown
### Covers

Shelfline caches OPDS and EPUB cover images under the configured library path at
`.shelfline/covers/`. Cover rendering is optional. When terminal graphics are
available and `preferences.covers.display` is `auto`, detail panels may render
the cover image. Otherwise Shelfline shows a polished text fallback.

Cover preferences:

```json
{
  "preferences": {
    "covers": {
      "display": "auto",
      "prefer_thumbnails": true
    }
  }
}
```

### Reader Preferences And Zen Mode

Reader preferences live in the JSON config:

```json
{
  "preferences": {
    "reader": {
      "width": "medium",
      "theme": "default",
      "paragraph_spacing": "normal",
      "show_progress": true,
      "show_chapter_title": true,
      "zen_mode_default": false
    }
  }
}
```

Reader keys:

- `z`: toggle Zen Mode.
- `o`: open reader options.
- `g`: open bookmarks.
- `t`: open table of contents.
```

- [ ] **Step 2: Update screenshot notes**

Add to `docs/assets/screenshots/README.md`:

```markdown
For 0.2.0 screenshots, capture:

- catalog detail with cover fallback or image render
- library detail with cached cover metadata
- normal reader with configured spacing
- Zen Mode reader
- reader options or bookmark navigator
```

- [ ] **Step 3: Run markdown/diff check**

Run:

```powershell
git diff --check -- README.md docs/assets/screenshots/README.md
```

Expected: PASS.

- [ ] **Step 4: Commit docs**

```powershell
git add README.md docs/assets/screenshots/README.md
git commit -m "docs: document reading experience features"
```

---

## Task 15: Final Verification

**Files:**
- No code ownership unless fixing failures discovered by verification.

- [ ] **Step 1: Run focused suites**

Run:

```powershell
python -m pytest tests/test_config.py tests/test_covers.py tests/test_library.py tests/test_services.py tests/test_reader.py tests/test_reader_screen.py -v
```

Expected: PASS.

- [ ] **Step 2: Run TUI suites**

Run:

```powershell
python -m pytest tests/test_tui_smoke.py tests/test_tui_flows.py tests/test_tui_shell.py tests/test_tui_theme.py -v
```

Expected: PASS.

- [ ] **Step 3: Run full suite**

Run:

```powershell
python -m pytest -v
```

Expected: PASS.

- [ ] **Step 4: Run package smoke**

Run:

```powershell
python -m shelfline --help
```

Expected: command exits 0 and output mentions `--config`.

- [ ] **Step 5: Manual smoke**

Run `shelfline` from an installed or editable environment and verify:

- Fresh config opens setup.
- Add OPDS catalog.
- Browse nested OPDS folders.
- Select a book with cover metadata.
- Confirm detail panel shows cover fallback or image.
- Download EPUB.
- Open Library.
- Confirm cached cover metadata appears.
- Open Reader.
- Change width/theme/spacing.
- Toggle Zen Mode on and off.
- Open TOC and jump sections.
- Add bookmark, open bookmark navigator, jump bookmark.
- Close and reopen, confirming progress and preferences persist.
- Disable images with `preferences.covers.display = "text"` and confirm text fallback.

- [ ] **Step 6: Commit verification docs or fixes**

If documentation or bug fixes were needed during verification:

```powershell
git add README.md docs/assets/screenshots/README.md src tests
git commit -m "chore: finalize shelfline 0.2 verification"
```

If no changes were needed, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Visual polish and covers are covered by Tasks 2 through 7 and Task 14.
- Reader persisted preferences are covered by Tasks 1, 8, and 9.
- Zen Mode is covered by Task 10.
- TOC and bookmark navigation are covered by Tasks 11 and 12.
- EPUB text cleanup is covered by Task 13.
- Documentation, screenshots, and release verification are covered by Tasks 14
  and 15.

Scope boundaries:

- No OPDS 2.x work is included.
- No PDF, DjVu, CBR, or CBZ rendering is included.
- No multi-download queue is included.
- No sync, annotations, highlights, or full-text search is included.

Type consistency:

- `ReaderPreferences`, `CoverPreferences`, and `AppPreferences` are introduced
  in Task 1 and reused by later reader/TUI tasks.
- `thumbnail_url` and `cover_cache_status` are introduced in Task 3 before
  services and TUI consume them.
- `CoverCache`, `CoverError`, `cached_cover_path`, and `extract_epub_cover` are
  introduced in Task 2 before services use them.
- Reader preference updates consistently use `dataclasses.replace`.

Execution notes:

- Tasks are ordered so text fallback and cache behavior land before optional
  terminal image rendering.
- Each task has focused tests and a commit point.
- Existing `uv.lock` should remain untouched unless the user explicitly asks to
  track it.
