# Catalog Inline Details Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Shelfline's separate catalog book detail page with an inline right-hand details pane that constrains cover images and exposes download actions from the catalog feed screen.

**Architecture:** `FeedScreen` will adopt the existing `AppShell` two-pane layout used by the library and catalog-selection screens. A new catalog-entry detail widget will render folder/book details in the right pane, while `FeedScreen` owns selection, navigation, default download, and cover-cache orchestration.

**Tech Stack:** Python, Textual, Rich-compatible widgets, existing Shelfline `CatalogWorkflow`, existing pytest/Textual `run_test` test style.

---

## Scope Check

This plan implements one subsystem: catalog feed browsing and selected-entry details. It does not change library management, reader behavior, or the cover cache storage model.

## File Structure

- Modify `src/shelfline/tui/widgets.py`
  - Add `CatalogEntryDetailView`.
  - Reuse `CoverDisplay`, `AcquisitionRow`, `clean_opds_html_text`, and existing OPDS glyph labels.
  - Keep `EntryDetailView` for compatibility until tests prove it is no longer needed.
- Modify `src/shelfline/tui/screens.py`
  - Convert `FeedScreen` to `AppShell`.
  - Add a `d` binding and default acquisition download from the selected feed row.
  - Move catalog cover fetch/update behavior from `EntryScreen` into `FeedScreen`.
- Modify `src/shelfline/tui/app.tcss`
  - Add constrained catalog detail and cover styles.
- Modify `tests/test_tui_flows.py`
  - Add tests for inline details, selection updates, folder details, default download, and stale-cover clearing.
  - Update tests that currently expect `EntryScreen` for normal book inspection.

---

### Task 1: Add Catalog Entry Detail Widget

**Files:**
- Modify: `src/shelfline/tui/widgets.py`
- Test: `tests/test_tui_flows.py`

- [ ] **Step 1: Write failing widget-level flow tests**

Add these tests near the existing feed/catalog screen tests in `tests/test_tui_flows.py`:

```python
@pytest.mark.asyncio
async def test_feed_screen_renders_selected_book_in_detail_pane() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(FeedScreen(_feed()))
        rendered = str(app.screen.query_one("#catalog-entry-detail").renderable)

    assert "Interesting Book" in rendered
    assert "Ada Lovelace" in rendered
    assert "A small but useful book." in rendered
    assert "EPUB" in rendered
    assert "PDF" in rendered
    assert "d download" in rendered


@pytest.mark.asyncio
async def test_feed_screen_renders_folder_detail_without_book_noise() -> None:
    feed = CatalogFeed(
        title="Root Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_navigation_entry()],
    )
    app = ShelflineApp(config=None)

    async with app.run_test():
        await app.push_screen(FeedScreen(feed))
        rendered = str(app.screen.query_one("#catalog-entry-detail").renderable)

    assert "Fiction" in rendered
    assert "Enter open" in rendered
    assert "Unknown author" not in rendered
    assert "Cover" not in rendered
    assert "download" not in rendered.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m pytest tests/test_tui_flows.py::test_feed_screen_renders_selected_book_in_detail_pane tests/test_tui_flows.py::test_feed_screen_renders_folder_detail_without_book_noise -q
```

Expected: both tests fail because `#catalog-entry-detail` does not exist.

- [ ] **Step 3: Implement `CatalogEntryDetailView`**

In `src/shelfline/tui/widgets.py`, add this class after `EntryDetailView`:

```python
class CatalogEntryDetailView(VerticalScroll):
    def __init__(
        self,
        entry: CatalogEntry | None,
        *,
        cover_path: Path | None = None,
        cover_status: str | None = None,
        terminal_graphics: bool = False,
        display_mode: str = "auto",
        source: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(id="catalog-entry-detail", classes="catalog-entry-detail", **kwargs)
        self.entry = entry
        self.cover_path = cover_path
        self.cover_status = cover_status
        self.terminal_graphics = terminal_graphics
        self.display_mode = display_mode
        self.source = source

    @property
    def renderable(self) -> str:
        return self.render_text(self.entry)

    def compose(self) -> ComposeResult:
        yield from self._widgets()

    def set_entry(
        self,
        entry: CatalogEntry | None,
        *,
        cover_path: Path | None = None,
        cover_status: str | None = None,
        terminal_graphics: bool | None = None,
        display_mode: str | None = None,
        source: str | None = None,
    ) -> None:
        self.entry = entry
        self.cover_path = cover_path
        self.cover_status = cover_status
        if terminal_graphics is not None:
            self.terminal_graphics = terminal_graphics
        if display_mode is not None:
            self.display_mode = display_mode
        self.source = source
        if self.is_mounted:
            self.remove_children()
            self.mount_all(self._widgets())

    def _widgets(self) -> list[Widget]:
        if self.entry is None:
            return [Static(f"{glyph(ENTRY_LABEL)} No entry selected", classes="empty-state")]
        if self.entry.navigation_url is not None or not self.entry.acquisition_links:
            return self._folder_widgets(self.entry)
        return self._book_widgets(self.entry)

    def _folder_widgets(self, entry: CatalogEntry) -> list[Widget]:
        widgets: list[Widget] = [
            Static(f"{glyph(FOLDER_LABEL)} {entry.title}", classes="entry-title"),
        ]
        if entry.updated:
            widgets.append(Static(f"Updated: {entry.updated}", classes="entry-updated"))
        if entry.navigation_url:
            widgets.append(Static(entry.navigation_url, classes="entry-updated"))
        widgets.append(Static("Enter open", classes="catalog-detail-hint"))
        return widgets

    def _book_widgets(self, entry: CatalogEntry) -> list[Widget]:
        cover = CoverDisplay(
            title=entry.title,
            authors=entry.authors,
            image_path=self.cover_path,
            terminal_graphics=self.terminal_graphics,
            display_mode=self.display_mode,
            media_type=self._primary_media_type(entry),
            source=self.source,
            cache_status=self.cover_status,
            cover_url=entry.cover_image_url or entry.thumbnail_url,
            classes="catalog-cover-display",
        )
        widgets: list[Widget] = [
            Container(cover, classes="catalog-cover-box"),
            Static(entry.title, classes="entry-title"),
            Static(self._authors_text(entry), classes="entry-authors"),
        ]
        if entry.updated:
            widgets.append(Static(f"Updated: {entry.updated}", classes="entry-updated"))
        summary = clean_opds_html_text(entry.summary or "")
        if summary:
            widgets.extend(
                [
                    Static("Description", classes="entry-section-title"),
                    Static(summary, classes="entry-summary"),
                ]
            )
        widgets.append(Static(f"{DOWNLOADS_LABEL.text} - d download", classes="entry-section-title"))
        if not entry.acquisition_links:
            widgets.append(Static("No downloads available", classes="empty-state"))
        else:
            widgets.extend(
                AcquisitionRow(link, index=index, selected=index == 0)
                for index, link in enumerate(entry.acquisition_links)
            )
        return widgets

    @staticmethod
    def _authors_text(entry: CatalogEntry) -> str:
        return ", ".join(entry.authors) if entry.authors else "Unknown author"

    @staticmethod
    def _primary_media_type(entry: CatalogEntry) -> str | None:
        link = entry.best_epub_link() or (entry.acquisition_links[0] if entry.acquisition_links else None)
        return link.media_type if link is not None else None

    @staticmethod
    def render_text(entry: CatalogEntry | None) -> str:
        if entry is None:
            return f"{glyph(ENTRY_LABEL)} No entry selected"
        if entry.navigation_url is not None or not entry.acquisition_links:
            lines = [f"{glyph(FOLDER_LABEL)} {entry.title}"]
            if entry.updated:
                lines.append(f"Updated: {entry.updated}")
            if entry.navigation_url:
                lines.append(entry.navigation_url)
            lines.append("Enter open")
            return "\n".join(lines)
        lines = [entry.title, CatalogEntryDetailView._authors_text(entry)]
        summary = clean_opds_html_text(entry.summary or "")
        if summary:
            lines.extend(["Description:", summary])
        lines.append(f"{DOWNLOADS_LABEL.text} - d download")
        for index, link in enumerate(entry.acquisition_links):
            lines.append(AcquisitionRow(link, index=index, selected=index == 0).renderable)
        return "\n".join(lines)
```

Also add `Widget` to the Textual imports if it is not already imported:

```python
from textual.widget import Widget
```

- [ ] **Step 4: Wire the import only**

In `src/shelfline/tui/screens.py`, add `CatalogEntryDetailView` to the widget import list:

```python
from shelfline.tui.widgets import (
    BusyIndicator,
    CoverDisplay,
    CatalogEntryDetailView,
    CatalogList,
    EntryDetailView,
    FeedEntryList,
    LibraryBookList,
    LibraryDetailView,
    DownloadProgressDisplay,
    StatusLine,
)
```

- [ ] **Step 5: Run tests to verify current failures are only screen wiring**

Run:

```powershell
python -m pytest tests/test_tui_flows.py::test_feed_screen_renders_selected_book_in_detail_pane tests/test_tui_flows.py::test_feed_screen_renders_folder_detail_without_book_noise -q
```

Expected: tests may still fail because `FeedScreen` does not mount `CatalogEntryDetailView`; import/type errors should not occur.

- [ ] **Step 6: Commit widget work**

Run:

```powershell
git add src/shelfline/tui/widgets.py src/shelfline/tui/screens.py tests/test_tui_flows.py
git commit -m "feat: add catalog entry detail widget"
```

---

### Task 2: Convert FeedScreen To Two-Pane Layout

**Files:**
- Modify: `src/shelfline/tui/screens.py`
- Test: `tests/test_tui_flows.py`

- [ ] **Step 1: Update `FeedScreen.compose` to use `AppShell`**

Replace the current `FeedScreen.compose` method with:

```python
def compose(self) -> ComposeResult:
    yield AppShell(area="Catalog", key_hints=self.KEY_HINT)
```

- [ ] **Step 2: Add `FeedScreen.on_mount` region population**

Add this method to `FeedScreen`:

```python
def on_mount(self) -> None:
    replace_region(
        self.query_one("#main-region"),
        FeedEntryList(
            breadcrumbs=self.breadcrumbs,
            source_url=self.feed.source_url,
            updated=self.feed.updated,
            entries=self.feed.entries,
            selected_index=self.selected_index,
        ),
        BusyIndicator(id="busy-indicator"),
    )
    replace_region(
        self.query_one("#detail-region"),
        self._detail_view(),
        StatusLine("Ready", id="status-line"),
    )
    self._start_selected_cover_fetch()
```

- [ ] **Step 3: Add selected-entry helpers**

Add these methods to `FeedScreen`:

```python
@property
def selected_entry(self) -> CatalogEntry | None:
    if not self.feed.entries:
        return None
    index = min(self.selected_index, len(self.feed.entries) - 1)
    return self.feed.entries[index]

def _detail_view(self) -> CatalogEntryDetailView:
    return CatalogEntryDetailView(
        self.selected_entry,
        terminal_graphics=_cover_terminal_graphics(getattr(self.app, "config", None)),
        display_mode=_cover_display_mode(getattr(self.app, "config", None)),
        source=self.catalog.name if self.catalog is not None else None,
    )

def _refresh_detail(self) -> None:
    detail = self.query_one("#catalog-entry-detail", CatalogEntryDetailView)
    detail.set_entry(
        self.selected_entry,
        cover_path=None,
        cover_status=None,
        terminal_graphics=_cover_terminal_graphics(getattr(self.app, "config", None)),
        display_mode=_cover_display_mode(getattr(self.app, "config", None)),
        source=self.catalog.name if self.catalog is not None else None,
    )
```

- [ ] **Step 4: Update selection movement**

Modify `FeedScreen._move_selection` so it updates the detail pane and clears stale cover state:

```python
def _move_selection(self, delta: int) -> None:
    if not self.feed.entries:
        return
    self.selected_index = max(0, min(len(self.feed.entries) - 1, self.selected_index + delta))
    self.query_one("#feed-body", FeedEntryList).set_selected_index(self.selected_index)
    self._refresh_detail()
    entry = self.feed.entries[self.selected_index]
    self.query_one("#status-line", StatusLine).set_message(f"Selected {entry.title}")
    self._start_selected_cover_fetch()
```

- [ ] **Step 5: Update tests that expect book Enter to open EntryScreen**

Replace `test_feed_screen_opens_entry_details` with:

```python
@pytest.mark.asyncio
async def test_feed_screen_keeps_book_details_inline_on_enter() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(_feed()))
        await app.screen.open_entry(0)
        await pilot.pause()

        assert isinstance(app.screen, FeedScreen)
        assert "Interesting Book" in str(app.screen.query_one("#catalog-entry-detail").renderable)
        assert "d download" in str(app.screen.query_one("#catalog-entry-detail").renderable)
```

Update `test_feed_screen_enter_binding_opens_entry_details` similarly:

```python
@pytest.mark.asyncio
async def test_feed_screen_enter_binding_keeps_book_details_inline() -> None:
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(_feed()))
        await pilot.press("enter")

        assert isinstance(app.screen, FeedScreen)
        assert "Interesting Book" in str(app.screen.query_one("#catalog-entry-detail").renderable)
```

- [ ] **Step 6: Change book `open_entry` behavior**

Modify the non-navigation branch of `FeedScreen.open_entry`:

```python
        self.finish_outgoing_call("Use d to download this book")
```

The full method should still navigate when `entry.navigation_url is not None`.

- [ ] **Step 7: Run feed layout tests**

Run:

```powershell
python -m pytest tests/test_tui_flows.py -k "feed_screen" -q
```

Expected: feed screen tests pass or reveal only cover/download tests that are handled in later tasks.

- [ ] **Step 8: Commit two-pane layout**

Run:

```powershell
git add src/shelfline/tui/screens.py tests/test_tui_flows.py
git commit -m "feat: show catalog entry details inline"
```

---

### Task 3: Add FeedScreen Download Action

**Files:**
- Modify: `src/shelfline/tui/screens.py`
- Test: `tests/test_tui_flows.py`

- [ ] **Step 1: Add failing download tests**

Add these tests near existing feed screen tests:

```python
@pytest.mark.asyncio
async def test_feed_screen_downloads_selected_book_with_d_key() -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow(download_path=Path("downloaded.epub"))
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(_feed(), catalog=catalog, workflow=workflow))
        await pilot.press("d")
        await pilot.pause()

    assert workflow.downloads == [(catalog, _feed().entries[0], _feed().entries[0].best_epub_link())]


@pytest.mark.asyncio
async def test_feed_screen_download_key_reports_no_download_for_folder() -> None:
    feed = CatalogFeed(
        title="Root Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[_navigation_entry()],
    )
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    workflow = FakeWorkflow()
    app = ShelflineApp(config=None)

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.press("d")
        status = str(app.screen.query_one("#status-line").renderable)

    assert workflow.downloads == []
    assert "no downloads" in status.lower()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_tui_flows.py::test_feed_screen_downloads_selected_book_with_d_key tests/test_tui_flows.py::test_feed_screen_download_key_reports_no_download_for_folder -q
```

Expected: fail because the feed screen has no `d` binding/action.

- [ ] **Step 3: Add binding and key hint**

Update `FeedScreen.KEY_HINT`:

```python
KEY_HINT = "Keys: enter open | d download | j/k select | b back | c catalogs | l library"
```

Update `FeedScreen.BINDINGS`:

```python
BINDINGS = [
    ("enter", "open_selected", "Open"),
    ("d", "download_selected", "Download"),
    ("b", "go_back", "Back"),
    ("j", "cursor_down", "Down"),
    ("down", "cursor_down", "Down"),
    ("k", "cursor_up", "Up"),
    ("up", "cursor_up", "Up"),
]
```

- [ ] **Step 4: Add default acquisition helper**

Add this method to `FeedScreen`:

```python
def _selected_download_link(self) -> AcquisitionLink | None:
    entry = self.selected_entry
    if entry is None:
        return None
    return entry.best_epub_link() or (entry.acquisition_links[0] if entry.acquisition_links else None)
```

If `AcquisitionLink` is not imported in `screens.py`, import it:

```python
from shelfline.catalog.models import AcquisitionLink, CatalogEntry, CatalogFeed
```

- [ ] **Step 5: Add download action**

Add these methods to `FeedScreen`:

```python
async def download_selected_entry(self) -> None:
    if self.workflow is None or self.catalog is None:
        self.finish_outgoing_call("Download workflow is not available")
        return
    entry = self.selected_entry
    link = self._selected_download_link()
    if entry is None or link is None:
        self.finish_outgoing_call("Selected entry has no downloads")
        return

    status_screen = DownloadStatusScreen(status="Starting download...")
    await self.app.push_screen(status_screen)
    try:
        await self.workflow.download_acquisition(
            self.catalog,
            entry,
            link=link,
            on_status=status_screen.set_status,
            on_progress=lambda progress: status_screen.update_progress(progress),
        )
    except Exception as exc:
        status_screen.set_status(f"Download failed: {_error_message(exc)}")
        return
    status_screen.set_status("Download complete")

async def action_download_selected(self) -> None:
    await self.download_selected_entry()
```

- [ ] **Step 6: Run download tests**

Run:

```powershell
python -m pytest tests/test_tui_flows.py::test_feed_screen_downloads_selected_book_with_d_key tests/test_tui_flows.py::test_feed_screen_download_key_reports_no_download_for_folder -q
```

Expected: both tests pass.

- [ ] **Step 7: Run feed screen tests**

Run:

```powershell
python -m pytest tests/test_tui_flows.py -k "feed_screen" -q
```

Expected: feed screen tests pass.

- [ ] **Step 8: Commit download action**

Run:

```powershell
git add src/shelfline/tui/screens.py tests/test_tui_flows.py
git commit -m "feat: download selected catalog book inline"
```

---

### Task 4: Move Catalog Cover Fetch To Inline Detail Pane

**Files:**
- Modify: `src/shelfline/tui/screens.py`
- Test: `tests/test_tui_flows.py`

- [ ] **Step 1: Update cover tests to target inline pane**

Replace `test_entry_screen_fetches_catalog_cover_and_updates_display` with:

```python
@pytest.mark.asyncio
async def test_feed_screen_fetches_selected_book_cover_and_updates_detail(
    tmp_path: Path,
) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    cover_path = tmp_path / "covers" / "covered.jpg"
    cover_path.parent.mkdir()
    cover_path.write_bytes(b"cover")
    workflow = FakeWorkflow()
    workflow.catalog_cover_path = cover_path
    entry = CatalogEntry(
        title="Covered Book",
        identifier="urn:book:covered",
        updated="2026-05-30",
        authors=["Ada Lovelace"],
        cover_image_url="https://example.test/covers/covered.jpg",
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/covered.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    feed = CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[entry],
    )
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            catalogs=[catalog],
            preferences=AppPreferences(covers=CoverPreferences(display="auto")),
        ),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.pause()
        await pilot.pause()
        cover = app.screen.query_one("#catalog-entry-detail CoverDisplay", CoverDisplay)

    assert workflow.catalog_cover_requests == [(catalog, entry)]
    assert cover.image_path == cover_path
    assert cover.cache_status == "cached"
```

Add stale-cover clearing test:

```python
@pytest.mark.asyncio
async def test_feed_screen_clears_stale_cover_when_selection_moves(tmp_path: Path) -> None:
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    cover_path = tmp_path / "covers" / "covered.jpg"
    cover_path.parent.mkdir()
    cover_path.write_bytes(b"cover")
    first = CatalogEntry(
        title="Covered Book",
        identifier="urn:book:covered",
        updated=None,
        authors=["Ada Lovelace"],
        cover_image_url="https://example.test/covers/covered.jpg",
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/covered.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    second = CatalogEntry(
        title="Plain Book",
        identifier="urn:book:plain",
        updated=None,
        authors=["Grace Hopper"],
        acquisition_links=[
            AcquisitionLink(
                href="https://example.test/books/plain.epub",
                relation="http://opds-spec.org/acquisition",
                media_type="application/epub+zip",
                title="EPUB",
            )
        ],
    )
    workflow = FakeWorkflow()
    workflow.catalog_cover_path = cover_path
    feed = CatalogFeed(
        title="Example Feed",
        source_url="https://example.test/opds",
        updated=None,
        entries=[first, second],
    )
    app = ShelflineApp(
        config=AppConfig(
            library_path=tmp_path,
            catalogs=[catalog],
            preferences=AppPreferences(covers=CoverPreferences(display="auto")),
        ),
        workflow=workflow,
    )

    async with app.run_test() as pilot:
        await app.push_screen(FeedScreen(feed, catalog=catalog, workflow=workflow))
        await pilot.pause()
        await pilot.pause()
        await pilot.press("j")
        cover = app.screen.query_one("#catalog-entry-detail CoverDisplay", CoverDisplay)
        rendered = str(app.screen.query_one("#catalog-entry-detail").renderable)

    assert "Plain Book" in rendered
    assert cover.image_path is None
    assert cover.cache_status is None
```

- [ ] **Step 2: Run cover tests to verify failures**

Run:

```powershell
python -m pytest tests/test_tui_flows.py -k "selected_book_cover or clears_stale_cover" -q
```

Expected: fail until cover fetch is moved into `FeedScreen`.

- [ ] **Step 3: Add cover helper methods to `FeedScreen`**

Add these methods:

```python
def _selected_entry_cover_url(self) -> str | None:
    entry = self.selected_entry
    if entry is None or entry.navigation_url is not None:
        return None
    return entry.cover_image_url or entry.thumbnail_url

def _start_selected_cover_fetch(self) -> None:
    if self.workflow is None or self.catalog is None:
        return
    if self._selected_entry_cover_url() is None:
        return
    if _cover_display_mode(getattr(self.app, "config", None)) == "off":
        return
    self.run_worker(self._cache_selected_cover(self.selected_index), name="feed-cover", exclusive=True)

async def _cache_selected_cover(self, index: int) -> None:
    if self.workflow is None or self.catalog is None:
        return
    if index < 0 or index >= len(self.feed.entries):
        return
    entry = self.feed.entries[index]
    if entry.navigation_url is not None:
        return
    try:
        cover_path = await self.workflow.cache_catalog_entry_cover(self.catalog, entry)
    except Exception:
        return
    if cover_path is None or not self.is_mounted or index != self.selected_index:
        return
    detail = self.query_one("#catalog-entry-detail", CatalogEntryDetailView)
    detail.set_entry(
        entry,
        cover_path=cover_path,
        cover_status="cached",
        terminal_graphics=_cover_terminal_graphics(getattr(self.app, "config", None)),
        display_mode=_cover_display_mode(getattr(self.app, "config", None)),
        source=self.catalog.name if self.catalog is not None else None,
    )
```

- [ ] **Step 4: Remove redundant EntryScreen catalog cover fetch**

In `EntryScreen`, remove or stop using these methods for catalog preview covers:

```python
def on_mount(self) -> None:
    self._start_cover_fetch()
```

Also remove `_start_cover_fetch` and `_cache_entry_cover` from `EntryScreen` if `EntryScreen` is no longer used by normal catalog browsing. Keep `_cover_display` and `_update_cover_display` only if existing tests still need them.

- [ ] **Step 5: Run cover tests**

Run:

```powershell
python -m pytest tests/test_tui_flows.py -k "selected_book_cover or clears_stale_cover or entry_screen" -q
```

Expected: cover tests pass; remaining `EntryScreen` tests should still pass if the compatibility screen remains.

- [ ] **Step 6: Commit inline cover behavior**

Run:

```powershell
git add src/shelfline/tui/screens.py tests/test_tui_flows.py
git commit -m "fix: constrain catalog covers in detail pane"
```

---

### Task 5: Add Styling For Constrained Detail Pane

**Files:**
- Modify: `src/shelfline/tui/app.tcss`
- Test: `tests/test_tui_flows.py`

- [ ] **Step 1: Add CSS regression test**

Add this test to `tests/test_tui_flows.py`:

```python
def test_catalog_detail_styles_constrain_cover_area() -> None:
    css = Path("src/shelfline/tui/app.tcss").read_text(encoding="utf-8")

    assert ".catalog-entry-detail" in css
    assert ".catalog-cover-box" in css
    assert "max-height:" in css
    assert "height:" in css
```

- [ ] **Step 2: Run CSS test to verify failure**

Run:

```powershell
python -m pytest tests/test_tui_flows.py::test_catalog_detail_styles_constrain_cover_area -q
```

Expected: fail until CSS classes are added.

- [ ] **Step 3: Add CSS styles**

Append this to `src/shelfline/tui/app.tcss` near the existing entry/detail styles:

```css
.catalog-entry-detail {
    height: 1fr;
    padding: 0 1;
}

.catalog-cover-box {
    height: 10;
    max-height: 10;
    width: 100%;
    margin: 0 0 1 0;
    padding: 0 1;
    border-bottom: solid $primary;
}

.catalog-cover-display {
    height: 9;
    max-height: 9;
    width: 100%;
}

.catalog-detail-hint {
    margin: 1 0 0 0;
    color: $text-muted;
}
```

- [ ] **Step 4: Run CSS test**

Run:

```powershell
python -m pytest tests/test_tui_flows.py::test_catalog_detail_styles_constrain_cover_area -q
```

Expected: pass.

- [ ] **Step 5: Run targeted TUI flow tests**

Run:

```powershell
python -m pytest tests/test_tui_flows.py -q
```

Expected: all TUI flow tests pass.

- [ ] **Step 6: Commit styling**

Run:

```powershell
git add src/shelfline/tui/app.tcss tests/test_tui_flows.py
git commit -m "style: constrain catalog cover pane"
```

---

### Task 6: Final Regression And Cleanup

**Files:**
- Modify only if regressions are found:
  - `src/shelfline/tui/screens.py`
  - `src/shelfline/tui/widgets.py`
  - `src/shelfline/tui/app.tcss`
  - `tests/test_tui_flows.py`

- [ ] **Step 1: Run focused flow suite**

Run:

```powershell
python -m pytest tests/test_tui_flows.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run full suite**

Run:

```powershell
python -m pytest -q
```

Expected: full suite passes with the current skipped count.

- [ ] **Step 3: Inspect git diff**

Run:

```powershell
git diff --stat
git diff -- src/shelfline/tui/screens.py src/shelfline/tui/widgets.py src/shelfline/tui/app.tcss tests/test_tui_flows.py
```

Expected: only catalog inline detail, cover constraint, and related tests changed.

- [ ] **Step 4: Verify no unrelated files are staged**

Run:

```powershell
git status --short --branch
```

Expected: no staged or unstaged tracked files except any intentional final cleanup. The existing untracked `uv.lock` may remain untracked and must not be committed unless the user explicitly asks.

- [ ] **Step 5: Commit any final cleanup**

If Step 3 revealed small cleanup edits, commit them:

```powershell
git add src/shelfline/tui/screens.py src/shelfline/tui/widgets.py src/shelfline/tui/app.tcss tests/test_tui_flows.py
git commit -m "test: cover catalog inline details flow"
```

If there are no cleanup edits, skip this commit.

---

## Self-Review

Spec coverage:

- Two-pane catalog browsing is covered by Tasks 1 and 2.
- Folder-specific details and no `Unknown author` noise are covered by Task 1.
- Inline download with `d` is covered by Task 3.
- Cover fetch, stale cover clearing, and constrained image display are covered by Tasks 4 and 5.
- Error handling for no workflow/no acquisition is covered by Task 3.
- Full verification is covered by Task 6.

Completion scan:

- This plan contains only concrete tasks, commands, and expected outcomes.
- Multi-acquisition keyboard selection is explicitly out of scope; the concrete behavior for this plan is default acquisition download.

Type consistency:

- `CatalogEntryDetailView` is consistently referenced as `#catalog-entry-detail`.
- `FeedScreen.selected_entry`, `_selected_download_link`, and `_start_selected_cover_fetch` are defined before use in later tasks.
- Existing `CatalogWorkflow.cache_catalog_entry_cover` from the cover-image fix remains the service boundary.
