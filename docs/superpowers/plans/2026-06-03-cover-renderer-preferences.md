# Cover Renderer Preferences Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a JSON-configurable cover image renderer so users can force `textual-image` TGP, Sixel, halfcell, Unicode, automatic, or text-only cover output.

**Architecture:** Extend typed cover preferences with a validated `renderer` value, then pass it through the existing TUI cover display pipeline. Keep `preferences.covers.display` responsible for whether covers are shown, and make the new `preferences.covers.renderer` responsible only for selecting the image widget when image rendering is allowed.

**Tech Stack:** Python 3.11, Textual, optional `textual-image`, pytest.

---

## File Structure

- Modify `src/shelfline/config.py`: add the `CoverPreferences.renderer` field, validation set, parsing, and JSON serialization.
- Modify `src/shelfline/tui/widgets.py`: add a `renderer` argument to `CoverDisplay`, choose the correct `textual_image.widget` class, and preserve text fallback behavior.
- Modify `src/shelfline/tui/screens.py`: add `_cover_renderer(config)` and pass it into every `CoverDisplay` and `CatalogEntryDetailView` creation/update path.
- Modify `tests/test_config.py`: cover default, accepted, rejected, round-trip, redact, and app catalog-add preservation behavior.
- Modify `tests/test_tui_smoke.py`: cover renderer class selection and `renderer="text"` behavior.
- Modify `tests/test_tui_flows.py`: cover screen-level renderer propagation for catalog detail, entry detail, and library detail.
- Modify `README.md`: document the renderer preference and the realistic terminal image quality story.

---

### Task 1: Config Renderer Preference

**Files:**
- Modify: `src/shelfline/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write failing config tests**

Add these imports in `tests/test_config.py` if they are not already present:

```python
from shelfline.config import AppConfig, CatalogConfig, ConfigError, default_config_path, load_config, redact_config, save_config
```

Extend `test_default_preferences_are_loaded_when_missing`:

```python
assert config.preferences.covers.renderer == "auto"
```

Extend `test_app_config_normalizes_raw_preference_dicts` by changing the raw covers dict and assertions:

```python
"covers": {"display": "text", "renderer": "sixel"},
```

```python
assert config.preferences.covers.display == "text"
assert config.preferences.covers.renderer == "sixel"
```

Extend `test_reader_and_cover_preferences_round_trip` by adding the renderer value:

```python
"covers": {
    "display": "text",
    "prefer_thumbnails": False,
    "renderer": "tgp",
},
```

and assert it is saved:

```python
assert saved["preferences"]["covers"]["renderer"] == "tgp"
```

Extend `test_redact_config_serializes_typed_preferences_and_extra_values` by adding the renderer value:

```python
"covers": {
    "display": "text",
    "prefer_thumbnails": False,
    "renderer": "unicode",
},
```

and update the expected covers payload:

```python
assert redacted["preferences"]["covers"] == {
    "display": "text",
    "prefer_thumbnails": False,
    "renderer": "unicode",
}
```

Extend `test_add_catalog_preserves_typed_preferences_from_loaded_config`:

```python
"covers": {"display": "text", "renderer": "halfcell"},
```

```python
assert app.config.preferences.covers.renderer == "halfcell"
```

Add these new tests:

```python
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
```

- [ ] **Step 2: Run config tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_config.py -q
```

Expected: failures mention `CoverPreferences` has no `renderer` attribute or saved covers JSON lacks `renderer`.

- [ ] **Step 3: Implement config support**

In `src/shelfline/config.py`, change `CoverPreferences`:

```python
@dataclass(frozen=True)
class CoverPreferences:
    display: str = "auto"
    prefer_thumbnails: bool = True
    renderer: str = "auto"
```

Add a renderer validation set beside `_COVER_DISPLAY`:

```python
_COVER_DISPLAY = {"auto", "text", "off"}
_COVER_RENDERERS = {"auto", "tgp", "sixel", "halfcell", "unicode", "text"}
```

Update `_parse_cover_preferences`:

```python
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
```

Update `_preferences_to_json`:

```python
payload["covers"] = {
    "display": preferences.covers.display,
    "prefer_thumbnails": preferences.covers.prefer_thumbnails,
    "renderer": preferences.covers.renderer,
}
```

- [ ] **Step 4: Run config tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_config.py -q
```

Expected: all config tests pass.

- [ ] **Step 5: Commit config support**

Run:

```powershell
git add src/shelfline/config.py tests/test_config.py
git commit -m "feat: add cover renderer config preference"
```

---

### Task 2: CoverDisplay Renderer Selection

**Files:**
- Modify: `src/shelfline/tui/widgets.py`
- Test: `tests/test_tui_smoke.py`

- [ ] **Step 1: Write failing widget tests**

Add imports at the top of `tests/test_tui_smoke.py`:

```python
import sys
import types
```

Add these tests near the existing `CoverDisplay` tests:

```python
@pytest.mark.parametrize(
    ("renderer", "expected_class"),
    [
        ("auto", "Image"),
        ("tgp", "TGPImage"),
        ("sixel", "SixelImage"),
        ("halfcell", "HalfcellImage"),
        ("unicode", "UnicodeImage"),
    ],
)
def test_cover_display_uses_configured_textual_image_renderer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    renderer: str,
    expected_class: str,
) -> None:
    image_path = tmp_path / "cover.jpg"
    image_path.write_bytes(b"fake image")
    calls: list[tuple[str, str]] = []

    class FakeImage:
        def __init__(self, path: str) -> None:
            calls.append((self.__class__.__name__, path))

        def add_class(self, _class_name: str) -> None:
            return None

    fake_module = types.ModuleType("textual_image.widget")
    for class_name in ["Image", "TGPImage", "SixelImage", "HalfcellImage", "UnicodeImage"]:
        setattr(fake_module, class_name, type(class_name, (FakeImage,), {}))
    monkeypatch.setitem(sys.modules, "textual_image.widget", fake_module)

    display = CoverDisplay(
        title="Renderer Book",
        authors=["Ada Lovelace"],
        image_path=image_path,
        terminal_graphics=True,
        display_mode="auto",
        renderer=renderer,
    )

    widget = display._image_widget()

    assert widget is not None
    assert calls == [(expected_class, str(image_path))]


def test_cover_display_text_renderer_does_not_import_textual_image(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image_path = tmp_path / "cover.jpg"
    image_path.write_bytes(b"fake image")
    monkeypatch.delitem(sys.modules, "textual_image.widget", raising=False)

    display = CoverDisplay(
        title="Text Renderer Book",
        authors=["Ada Lovelace"],
        image_path=image_path,
        terminal_graphics=True,
        display_mode="auto",
        renderer="text",
    )

    assert display._image_widget() is None
    assert "textual_image.widget" not in sys.modules


def test_cover_display_update_cover_updates_renderer(tmp_path: Path) -> None:
    image_path = tmp_path / "cover.jpg"
    image_path.write_bytes(b"fake image")
    display = CoverDisplay(
        title="Renderer Book",
        authors=["Ada Lovelace"],
        image_path=image_path,
        terminal_graphics=True,
        display_mode="auto",
        renderer="auto",
    )

    display.update_cover(
        title="Renderer Book",
        authors=["Ada Lovelace"],
        image_path=image_path,
        display_mode="auto",
        renderer="sixel",
        media_type="application/epub+zip",
        source="Example",
        cache_status="cached",
    )

    assert display.renderer == "sixel"
```

- [ ] **Step 2: Run widget tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_tui_smoke.py -q
```

Expected: failures mention unexpected `renderer` argument or missing `renderer` attribute.

- [ ] **Step 3: Implement renderer selection**

In `src/shelfline/tui/widgets.py`, update `CoverDisplay.__init__` to accept and store a renderer:

```python
        renderer: str = "auto",
```

```python
        self.renderer = renderer
```

Update `CoverDisplay.update_cover` signature:

```python
        renderer: str | None = None,
```

and store the new value:

```python
        if renderer is not None:
            self.renderer = renderer
```

Replace `_image_widget` with:

```python
    def _image_widget(self) -> Widget | None:
        if self.display_mode != "auto":
            return None
        if self.renderer == "text":
            return None
        if not self.terminal_graphics:
            return None
        if self.image_path is None or not self.image_path.exists():
            return None

        try:
            from textual_image import widget as image_widgets

            widget_class = {
                "auto": image_widgets.Image,
                "tgp": image_widgets.TGPImage,
                "sixel": image_widgets.SixelImage,
                "halfcell": image_widgets.HalfcellImage,
                "unicode": image_widgets.UnicodeImage,
            }.get(self.renderer, image_widgets.Image)
            return widget_class(str(self.image_path))
        except Exception:
            return None
```

- [ ] **Step 4: Run widget tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_tui_smoke.py -q
```

Expected: all TUI smoke tests pass.

- [ ] **Step 5: Commit widget renderer selection**

Run:

```powershell
git add src/shelfline/tui/widgets.py tests/test_tui_smoke.py
git commit -m "feat: select cover image renderer"
```

---

### Task 3: Screen Renderer Plumbing

**Files:**
- Modify: `src/shelfline/tui/screens.py`
- Modify: `src/shelfline/tui/widgets.py`
- Test: `tests/test_tui_flows.py`

- [ ] **Step 1: Write failing screen propagation tests**

Add these tests to `tests/test_tui_flows.py` near the existing cover preference tests:

```python
@pytest.mark.asyncio
async def test_entry_screen_passes_cover_renderer_preference(tmp_path: Path) -> None:
    feed = _feed()
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[catalog],
        preferences={"covers": {"display": "auto", "renderer": "sixel"}},
    )
    app = ShelflineApp(config=config)

    async with app.run_test():
        await app.push_screen(FeedScreen(feed, catalog=catalog))
        cover = app.screen.query_one("#catalog-entry-detail").query_one(CoverDisplay)

    assert cover.renderer == "sixel"


@pytest.mark.asyncio
async def test_catalog_entry_screen_passes_cover_renderer_preference(tmp_path: Path) -> None:
    entry = _entry()
    catalog = CatalogConfig(name="Example", url="https://example.test/opds")
    config = AppConfig(
        library_path=tmp_path,
        catalogs=[catalog],
        preferences={"covers": {"display": "auto", "renderer": "tgp"}},
    )
    app = ShelflineApp(config=config)

    async with app.run_test():
        await app.push_screen(EntryScreen(entry, catalog=catalog))
        cover = app.screen.query_one("#cover-display", CoverDisplay)

    assert cover.renderer == "tgp"


@pytest.mark.asyncio
async def test_library_detail_passes_cover_renderer_preference(tmp_path: Path) -> None:
    book_path = tmp_path / "book.epub"
    book_path.write_bytes(b"book")
    cover_path = tmp_path / "cover.jpg"
    cover_path.write_bytes(b"cover")
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(
        BookRecord(
            title="Library Book",
            authors=["Ada Lovelace"],
            identifiers=[],
            source_catalog="Example",
            source_entry_url="https://example.test/book",
            acquisition_url="https://example.test/book.epub",
            media_type="application/epub+zip",
            cover_image_url="https://example.test/cover.jpg",
            cover_image_path=cover_path,
            local_file_path=book_path,
        )
    )
    config = AppConfig(
        library_path=tmp_path,
        preferences={"covers": {"display": "auto", "renderer": "halfcell"}},
    )
    app = ShelflineApp(config=config, library=repo)

    async with app.run_test():
        cover = app.screen.query_one("#cover-display", CoverDisplay)

    assert cover.renderer == "halfcell"
```

- [ ] **Step 2: Run flow tests and verify they fail**

Run:

```powershell
python -m pytest tests/test_tui_flows.py -q
```

Expected: failures mention `CoverDisplay` renderer remains `"auto"` instead of the configured value, or helper import/name issues that must be corrected to the existing test helper names.

- [ ] **Step 3: Pass renderer through catalog detail view**

In `src/shelfline/tui/widgets.py`, update `CatalogEntryDetailView.__init__`:

```python
        renderer: str = "auto",
```

```python
        self.renderer = renderer
```

Update `CatalogEntryDetailView.set_entry`:

```python
        renderer: str | None = None,
```

```python
        if renderer is not None:
            self.renderer = renderer
```

Update `CatalogEntryDetailView.update_cover`:

```python
        renderer: str,
```

```python
        self.renderer = renderer
```

Pass `renderer` to `cover.update_cover(...)`:

```python
            renderer=renderer,
```

Pass `renderer` to the `CoverDisplay` in `_book_widgets`:

```python
            renderer=self.renderer,
```

- [ ] **Step 4: Add screen helper and pass renderer everywhere**

In `src/shelfline/tui/screens.py`, add this helper near `_cover_display_mode`:

```python
def _cover_renderer(config: AppConfig | None) -> str:
    preferences = getattr(config, "preferences", None)
    if isinstance(preferences, AppPreferences):
        return preferences.covers.renderer
    return "auto"
```

Update each `CatalogEntryDetailView(...)`, `detail.set_entry(...)`, `detail.update_cover(...)`, `CoverDisplay(...)`, and `cover.update_cover(...)` call in `src/shelfline/tui/screens.py` to include:

```python
renderer=_cover_renderer(getattr(self.app, "config", None)),
```

This includes these methods:

```text
FeedScreen._detail_view
FeedScreen._refresh_detail
FeedScreen._cache_selected_cover
EntryScreen._cover_display
EntryScreen._update_cover_display
EntryScreen._cache_entry_cover
LibraryScreen._cover_display
LibraryScreen._update_cover_display
```

- [ ] **Step 5: Run flow tests and verify they pass**

Run:

```powershell
python -m pytest tests/test_tui_flows.py -q
```

Expected: all TUI flow tests pass.

- [ ] **Step 6: Commit screen renderer plumbing**

Run:

```powershell
git add src/shelfline/tui/screens.py src/shelfline/tui/widgets.py tests/test_tui_flows.py
git commit -m "feat: apply cover renderer preference in TUI"
```

---

### Task 4: README and Full Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README requirements and config docs**

In `README.md`, replace the current terminal graphics paragraph under `## Requirements` with:

````markdown
Terminal graphics cover rendering is optional. Install the `images` extra to
enable the optional `textual-image` dependency:

```shell
python -m pip install "shelfline[images]"
```

For the clearest cover images, use a terminal that supports a real raster image
protocol and set `preferences.covers.renderer` to match it. `tgp` targets the
Kitty Terminal Graphics Protocol, and `sixel` targets Sixel-capable terminals.
`halfcell` and `unicode` are portable terminal-cell approximations, so they are
useful fallbacks but are not pixel-perfect. The default `auto` lets
`textual-image` choose the renderer.
````

Update the cover preference example to include the renderer:

```json
{
  "preferences": {
    "covers": {
      "display": "auto",
      "prefer_thumbnails": true,
      "renderer": "auto"
    },
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

Below that example, add:

```markdown
Cover `display` accepts `auto`, `text`, or `off`. Cover `renderer` accepts
`auto`, `tgp`, `sixel`, `halfcell`, `unicode`, or `text`. Use `renderer: "text"`
when you want cover metadata/status without mounting any terminal image widget.
```

Update the usage cover-art paragraph to mention renderer selection:

```markdown
Catalog and library detail panes can show cached cover metadata and optional
cover art. Covers are cached below the configured library path in
`.shelfline/covers/`; when cover display is enabled and image rendering is
unavailable, Shelfline shows a text fallback designed for terminals. Set
`preferences.covers.renderer` to `tgp` or `sixel` for high-fidelity output on
compatible terminals, or set `preferences.covers.display` to `off` to disable
cover display entirely.
```

- [ ] **Step 2: Run documentation-related smoke checks**

Run:

```powershell
rg "preferences\.covers\.renderer|sixel|tgp|halfcell|unicode|shelfline\[images\]" README.md
```

Expected: output includes the new renderer config and image quality documentation.

- [ ] **Step 3: Run full tests**

Run:

```powershell
python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Run CLI smoke check**

Run:

```powershell
python -m shelfline --help
```

Expected: command exits successfully and shows Shelfline CLI help.

- [ ] **Step 5: Commit docs and verification**

Run:

```powershell
git add README.md
git commit -m "docs: explain cover renderer options"
```

---

## Final Review Checklist

- [ ] `preferences.covers.renderer` defaults to `"auto"` for old configs.
- [ ] Invalid renderer values raise `ConfigError` naming `preferences.covers.renderer`.
- [ ] Saved/redacted config JSON includes `preferences.covers.renderer`.
- [ ] `renderer="text"` does not import or mount `textual-image`.
- [ ] `auto`, `tgp`, `sixel`, `halfcell`, and `unicode` select the intended `textual-image` widget class.
- [ ] Catalog inline details, catalog entry screen, and library detail screen pass the configured renderer.
- [ ] Missing optional image support or renderer construction failure falls back to text/status.
- [ ] README explains optional install, renderer values, and terminal fidelity expectations.
- [ ] `python -m pytest -q` passes.
- [ ] `python -m shelfline --help` passes.
