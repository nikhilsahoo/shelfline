# Cover Renderer Preferences Design

Date: 2026-06-03
Project: Shelfline
Status: Draft for user review

## Goal

Shelfline should let users choose the terminal image renderer used for book covers, so users with raster-capable terminals can prefer the clearest available image output while users on simpler terminals keep a safe fallback.

## Background

Shelfline already supports optional cover image rendering through `textual-image`. The installed package exposes these widget classes:

- `Image` for automatic renderer selection.
- `TGPImage` for Terminal Graphics Protocol rendering.
- `SixelImage` for Sixel rendering.
- `HalfcellImage` for block-cell approximation.
- `UnicodeImage` for Unicode approximation.

The Kitty terminal graphics protocol is a raster graphics protocol for terminals, and Sixel is another terminal bitmap graphics format supported by some terminals. Those protocol-backed renderers can show real image pixels. Halfcell and Unicode renderers approximate images using terminal cells, so they cannot be pixel-perfect.

References:

- Kitty terminal graphics protocol: https://sw.kovidgoyal.net/kitty/graphics-protocol/
- textual-image package: https://pypi.org/project/textual-image/
- libsixel project: https://github.com/saitoha/libsixel

## User-Facing Configuration

Add `preferences.covers.renderer` to the JSON config.

Example:

```json
{
  "preferences": {
    "covers": {
      "display": "auto",
      "prefer_thumbnails": true,
      "renderer": "auto"
    }
  }
}
```

Allowed values:

- `auto`: Let `textual-image` choose the best renderer it can use.
- `tgp`: Force Terminal Graphics Protocol rendering.
- `sixel`: Force Sixel rendering.
- `halfcell`: Force terminal half-cell approximation.
- `unicode`: Force Unicode approximation.
- `text`: Do not mount an image widget; show cover text/status only.

Default: `auto`.

## Expected Quality

The app should describe image quality honestly:

- `tgp` and `sixel` are the preferred options for high-fidelity cover display.
- `halfcell` and `unicode` are portable approximations and should not be described as pixel-perfect.
- `auto` is the safest default because it lets `textual-image` select a renderer based on environment support.
- `text` remains useful when image rendering is distracting, slow, unsupported, or visually poor.

## Architecture

### Config

Extend `CoverPreferences` with:

```python
renderer: str = "auto"
```

Validation should accept only:

```python
{"auto", "tgp", "sixel", "halfcell", "unicode", "text"}
```

Saving config should preserve the renderer value under `preferences.covers.renderer`.

Existing config files without `renderer` should continue loading with `renderer = "auto"`.

### TUI Cover Display

`CoverDisplay` should accept a new `renderer` argument with default `"auto"`.

`CoverDisplay._image_widget()` should choose the widget class from `textual_image.widget`:

- `auto` -> `Image`
- `tgp` -> `TGPImage`
- `sixel` -> `SixelImage`
- `halfcell` -> `HalfcellImage`
- `unicode` -> `UnicodeImage`
- `text` -> no image widget

If importing `textual-image`, constructing the selected widget, or rendering with a specific backend fails, Shelfline should fall back to the existing text/status display without crashing.

### Screen Integration

The existing cover preference plumbing should pass `renderer` from config into all `CoverDisplay` instances:

- catalog inline details pane
- catalog entry compatibility screen
- library detail pane

The existing `display` preference keeps its current meaning:

- `display = "off"` hides cover display entirely.
- `display = "text"` shows metadata/status only.
- `display = "auto"` allows image rendering when possible.

The new `renderer` preference controls which image widget is used when image rendering is allowed.

## Error Handling

- Invalid config values should raise `ConfigError` with a clear message naming `preferences.covers.renderer`.
- Missing optional `textual-image` should not crash; cover display should fall back to text/status.
- A forced renderer that fails should not crash; cover display should fall back to text/status.
- `renderer = "text"` should be deterministic and should never attempt to import `textual-image`.

## Testing

Add tests for:

- Default config loads with `covers.renderer == "auto"`.
- Config parsing accepts every allowed renderer.
- Config parsing rejects invalid renderer values.
- Config saving includes `renderer`.
- `CoverDisplay` chooses the expected `textual_image.widget` class for each renderer using monkeypatched fake widget classes.
- `renderer = "text"` returns no image widget and does not import `textual-image`.
- Screens pass the configured renderer into catalog and library `CoverDisplay` instances.
- Existing cover fallback behavior still passes when `textual-image` is unavailable.

## Documentation

Update README cover/image notes with:

- `pip install "shelfline[images]"` for image support if not already documented.
- A short explanation of `preferences.covers.renderer`.
- A terminal-quality note: TGP/Kitty-compatible and Sixel-capable terminals can provide higher-fidelity images; halfcell/unicode are approximations.

## Out Of Scope

- Building a custom renderer outside `textual-image`.
- Detecting exact terminal support ourselves.
- Guaranteeing pixel-perfect output on terminals that do not support raster graphics protocols.
- Resizing or transforming cached cover image files on disk.
- Adding an in-app preferences editor.

## Acceptance Criteria

- Users can set `preferences.covers.renderer` in JSON config.
- Forced renderer modes select the corresponding `textual-image` widget.
- `renderer = "text"` disables image widgets without disabling cover metadata/status.
- Existing configs continue working.
- Catalog and library cover displays use the configured renderer.
- README explains when pixel-perfect or near-pixel-perfect terminal images are realistic.
- Full test suite passes.
