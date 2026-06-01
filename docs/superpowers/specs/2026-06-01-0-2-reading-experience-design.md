# Shelfline 0.2.0 Reading Experience Design

## Goal

Shelfline 0.2.0 is the reading experience release. It makes the app more
polished, personal, and book-like while keeping the 0.1.0 foundation intact:
OPDS 1.x catalogs, single downloads, local library management, EPUB reading,
JSON configuration, SQLite local state, and Windows/Linux support.

The release focuses on two product themes:

- Visual polish and covers.
- Reader comfort.

0.2.0 should make Shelfline nicer to look at and nicer to read in without
expanding into heavy new format rendering or new catalog protocols.

## Scope

Included in 0.2.0:

- OPDS and EPUB cover discovery, caching, and display.
- Conservative terminal image rendering in bounded detail panels.
- Polished text fallback for terminals without image support.
- Persisted reader preferences in JSON config.
- Reader layout controls for width, theme, paragraph spacing, progress, and
  chapter-title visibility.
- Reader Zen Mode.
- Improved EPUB table-of-contents and bookmark navigation.
- Better EPUB text cleanup.
- Documentation, tests, and screenshots for the upgraded reading experience.

Explicitly out of scope:

- OPDS 2.x.
- PDF, DjVu, CBR, and CBZ in-terminal rendering.
- Multiple simultaneous downloads or a download queue.
- Cloud sync, annotations, highlights, or full-text search.
- Mandatory terminal graphics support.

## Success Criteria

0.2.0 is complete when a user can install Shelfline, browse an OPDS catalog, see
covers where available, download a book, open the library, read EPUBs with
comfortable persisted preferences, use Zen Mode, navigate TOC/bookmarks
smoothly, and remain fully productive when their terminal does not support
images.

## Architecture

0.2.0 keeps Shelfline's existing layered architecture and adds two focused
capabilities: a cover pipeline and reader preferences.

Core module responsibilities:

- `catalog`: continue parsing OPDS 1.x cover and thumbnail links while
  preserving sanitized URLs.
- `downloads` and `services`: fetch cover assets opportunistically without
  making cover success required for book downloads.
- `library`: store local cover paths, cover cache status, reading
  progress, bookmarks, and per-book metadata.
- `config`: store stable user preferences in JSON under `preferences.reader`
  and `preferences.covers`.
- `reader`: improve EPUB text extraction and expose richer section/navigation
  data.
- `tui`: render cover-aware detail panels, reader preference controls, improved
  TOC/bookmark UI, Zen Mode, and fallback states.

JSON remains the human-editable preference/configuration store. SQLite remains
the app-managed store for per-book state, cache metadata, reading progress,
bookmarks, and read/unread state.

## Cover Pipeline

Cover sources:

- OPDS `http://opds-spec.org/image`.
- OPDS `http://opds-spec.org/image/thumbnail`.
- EPUB embedded cover image when available.
- Existing local cached cover path from the library database.

Caching behavior:

- Covers are stored under the configured library path at `.shelfline/covers/`.
- Cache filenames are deterministic and filesystem-safe, based on stable book
  identity or a hash of the source URL.
- A cached full cover is preferred over a thumbnail.
- Failed cover fetches do not break catalog browsing, downloads, or library
  opening.
- Missing cached cover paths are treated as cache misses.
- Auth-protected cover URLs use the same credential path as catalog feeds and
  downloads where applicable.

Rendering behavior:

- Use `textual-image` only in bounded detail areas, not in dense list rows.
- Candidate locations are catalog book detail panels, local library detail
  panels, and reader side/detail panels when terminal width allows.
- Never render images inside catalog or library rows.
- Terminal image rendering is optional and must degrade silently to text.

Reader and cover preferences include:

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

`covers.display` values:

- `auto`: attempt terminal image rendering and fall back to text.
- `text`: always show the polished text fallback.
- `off`: hide cover blocks except for minimal metadata where useful.

The fallback cover block should be designed rather than apologetic: title,
author, format/source, and compact cover status. Raw paths and exception text do
not belong in ordinary detail panes.

## Reader Preferences

Reader preferences are persisted in JSON under `preferences.reader`:

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

Suggested enum values:

- `width`: `narrow`, `medium`, `wide`.
- `theme`: `default`, `warm`, `high_contrast`.
- `paragraph_spacing`: `compact`, `normal`, `relaxed`.

Defaults should preserve the current readable constrained layout so existing
users are not surprised on upgrade.

Controls should be available from inside the reader through a compact
preferences overlay or command panel. Preference changes should save back to
JSON. If saving fails, the reader keeps the in-memory setting for the current
session and shows a recoverable status message.

Missing `preferences.reader` and `preferences.covers` blocks load defaults.
Known invalid enum values should fail config validation with clear errors.
Unknown preference keys should be ignored without failing when possible.

## Zen Mode

Zen Mode is a headline 0.2.0 reader feature.

Behavior:

- Toggle with `z` from the reader.
- Hide non-essential chrome: footer key hints, side/detail panels, secondary
  metadata, and noisy status regions.
- Keep reading text, configured width/theme/paragraph spacing, and optional
  minimal progress.
- Preserve the current section and scroll position when toggling.
- Use `preferences.reader.zen_mode_default` to decide whether new reader
  sessions begin in Zen Mode.
- Temporarily surface recoverable messages without permanently breaking the
  quiet layout.

Available controls in Zen Mode:

- `z`: exit Zen Mode.
- `b`: back.
- `q`: quit.
- `n` / `p`: next or previous section.
- Existing scroll/page keys.

Zen Mode is a display mode of the existing EPUB reader screen, not a separate
reader implementation. Progress, bookmarks, TOC jumps, and preferences remain
shared with the normal reader.

## Reader Comfort

Layout:

- Keep the centered reading surface.
- Make width, theme, paragraph spacing, progress visibility, and chapter-title
  visibility preference-driven.
- Maintain protected scrollbar gutter spacing.
- Avoid duplicate footers in normal and Zen modes.
- Ensure reader text does not collide with scrollbars, status, or side panels.

Navigation:

- Improve the TOC screen so section titles, the current marker, and progress are
  visually separated.
- Add a bookmarks list/navigator, not only bookmark add/remove.
- Support jump-to-TOC item, jump-to-bookmark, resume last position, next/previous
  section, and scroll/page movement.
- Jumping through TOC or bookmarks saves progress correctly.

Text cleanup:

- Improve paragraph separation.
- Improve heading extraction.
- Skip nav, guide, cover, titlepage-like, and other structural sections more
  reliably.
- Decode common HTML entities cleanly.
- Remove leftover HTML fragments such as `<br />` or escaped tags.
- Preserve deliberate paragraph breaks.
- Stay text-first; 0.2.0 does not promise rich EPUB layout.

## Data Model

JSON config owns stable user preferences:

- `preferences.reader.width`
- `preferences.reader.theme`
- `preferences.reader.paragraph_spacing`
- `preferences.reader.show_progress`
- `preferences.reader.show_chapter_title`
- `preferences.reader.zen_mode_default`
- `preferences.covers.display`
- `preferences.covers.prefer_thumbnails`

SQLite owns app-managed, per-book, and cache state:

- downloaded book metadata
- `cover_image_url`
- `thumbnail_url`
- `cover_image_path`
- cover cache status
- reading progress
- bookmarks
- read/unread state

Backward compatibility:

- Existing configs continue loading if preference blocks are missing.
- Existing books without local cover paths continue loading.
- Missing cached cover files are recoverable cache misses.

## Error Handling

Cover errors:

- Cover fetch failure must not block catalog browsing, book download, or library
  use.
- Image render failure must fall back to text without crashing the screen.
- Cover cache write failure should leave source metadata intact.
- Credentialed cover fetches must not leak usernames or passwords in status,
  logs, or cached URLs.

Reader preference errors:

- Invalid known config values produce clear config errors.
- Failure to save preferences does not close the reader.
- Zen Mode toggling never loses section or scroll position.

Reader content errors:

- Malformed EPUBs keep the existing recoverable reader error behavior.
- Empty or structural-only EPUBs explain that no readable text sections were
  found.
- TOC/bookmark jump failures leave the reader on the current section and show a
  status message.

Terminal compatibility:

- Windows and Linux remain primary targets.
- Terminal image support is optional.
- Plain terminals receive a good text UI.
- Users should not need to understand terminal graphics protocols to use
  Shelfline.

## Testing

Core tests:

- Preference defaults load when config has no reader/cover preferences.
- Valid reader/cover preferences round-trip through JSON.
- Invalid known preference values fail with clear messages.
- Cover cache paths are deterministic and safe.
- Cover fetch succeeds for public OPDS images.
- Cover fetch uses Basic Auth when needed.
- Cover fetch failure is recoverable.
- EPUB embedded cover extraction works when available.
- EPUB text cleanup removes leftover HTML while preserving paragraph breaks.
- Structural EPUB sections are skipped more reliably.

Library and state tests:

- Book metadata stores cached cover path.
- Existing books without cover path continue loading.
- Reading progress still saves/restores.
- Bookmarks still add/remove/list.
- Cover cache misses do not delete source cover metadata.

TUI tests:

- Catalog detail panel shows cover fallback.
- Library detail panel shows cached cover fallback/render target.
- Image rendering disabled preference shows text fallback.
- Reader preferences affect CSS/classes/layout state.
- Zen Mode hides non-essential chrome and preserves scroll/section.
- TOC current item remains visible and distinct.
- Bookmark navigator opens and jumps to the selected bookmark.
- No duplicate footers in normal or Zen Mode.

Manual smoke checklist:

- Install from PyPI.
- Launch with a fresh config.
- Add an OPDS catalog.
- Browse a nested catalog.
- Select a book with cover metadata.
- Confirm cover fallback or image render appears in a detail panel.
- Download an EPUB.
- Open Library and confirm cover/detail metadata.
- Open Reader.
- Change reader width/theme/spacing.
- Toggle Zen Mode on/off.
- Navigate TOC and bookmarks.
- Close and reopen, confirming preferences and progress persist.
- Confirm the app remains usable in a terminal without image support.

## Implementation Strategy

Recommended order:

1. Reader and cover preference model in JSON config.
2. Cover cache service and library metadata updates.
3. Cover display widget improvements with text fallback first.
4. Conservative `textual-image` rendering in detail panels.
5. Reader preference controls and layout/theme classes.
6. Zen Mode.
7. TOC and bookmark navigator polish.
8. EPUB text cleanup improvements.
9. Documentation, screenshots, release notes, and full verification.

The implementation should remain incremental and test-driven. Cover rendering
should land after text fallback and cache behavior are reliable, so terminal
graphics support remains a progressive enhancement rather than a dependency for
the rest of the release.

## Deferred After 0.2.0

- OPDS 2.x JSON feeds.
- PDF, DjVu, CBR, and CBZ rendering.
- Download queue.
- Full-text search inside books.
- Annotations and highlights.
- Sync and multi-device state.
- Collections, tags, and bulk library edits.
