# Catalog Inline Details Design

Date: 2026-06-02
Project: Shelfline
Status: Draft for user review

## Goal

Shelfline's catalog browsing should keep the user in the catalog list while showing useful book details and download actions in a right-hand pane. This replaces the current full-page catalog book detail flow where a rendered cover can consume the top of the screen and push the description out of view.

## Problem

Catalog book details currently live on a separate `EntryScreen`. That screen stacks the cover display above the textual details. Once cover images are fetched and displayed, the image can become too large and cover or displace the book description. The user has to leave the catalog list to inspect a book, then go back to continue browsing.

## Recommended Approach

Use the existing `AppShell` two-pane pattern for catalog feeds:

- Left pane: catalog entries, folders, and books.
- Right pane: details for the selected row.
- Bottom key hints: keep catalog actions visible and consistent.

This makes catalog browsing behave more like the library screen and keeps details close to the selected row.

## User Interaction

Catalog feed selection remains driven by `j/k` and arrow keys.

- Selecting a folder shows folder metadata and an `Enter open` hint in the detail pane.
- Selecting a book shows cover, metadata, description, and download options in the detail pane.
- `Enter` opens folders and navigation entries.
- `d` downloads the selected book's default acquisition.
- `b` goes back to the parent catalog screen.
- `c` opens catalog selection.
- `l` opens the local library.

For this release, download selection will use the same default acquisition logic already used by the workflow: prefer EPUB when available, otherwise use the first acquisition link. Showing all acquisition links in the detail pane is in scope, but keyboard selection between multiple acquisition links can remain a later refinement.

## Detail Pane Behavior

### Folder Or Navigation Row

The pane shows:

- Folder glyph and title.
- Updated date if available.
- Source or target URL when useful.
- `Enter open` hint.

It must not show `Unknown author`, acquisition controls, or cover status for folders.

### Book Row

The pane shows:

- Fixed-size cover area.
- Title and authors.
- Updated date if available.
- Media/acquisition summary.
- Cleaned OPDS description.
- Acquisition rows.
- `d download` hint.

If the entry has no acquisition links, the pane shows a clear `No downloads available` state and `d` should report that no acquisition is available.

## Cover Handling

The cover area must be constrained so it cannot obscure the description or resize the pane unexpectedly.

Rules:

- Use a dedicated cover container in the detail pane.
- Give the cover container stable dimensions with a maximum height and width.
- The image may be rendered only when terminal graphics are enabled and a local cached cover path exists.
- Before the cover is cached, show text status such as `Cover available` or `Cover unavailable`.
- After the cover is cached, show the image inside the constrained cover container and keep the description visible below it.
- When selection changes, clear the previous cover immediately so stale images do not appear for the next row.
- Do not fetch covers for folder/navigation rows.

The existing workflow cover-cache method can remain the service boundary for fetching catalog entry covers.

## Download Flow

The feed screen gains a `d` binding.

When the selected entry has acquisition links:

1. Start the existing download status screen.
2. Download the default acquisition through `CatalogWorkflow.download_acquisition`.
3. Preserve the existing progress/status behavior.
4. On completion, leave the user able to go to the library or return to the catalog.

When the selected entry is a folder/navigation row:

- `d` reports `Selected entry has no downloads`.

## Architecture

### FeedScreen

`FeedScreen` should compose through `AppShell` instead of manually stacking `Header`, `FeedEntryList`, `BusyIndicator`, `StatusLine`, and `KeyHintFooter`.

Left `main-region`:

- `FeedEntryList`
- `BusyIndicator`

Right `detail-region`:

- New selected-entry detail widget.
- `StatusLine`

The screen owns selection, navigation, download, and cover-fetch orchestration.

### New Or Updated Widgets

Add a selected-entry detail widget, likely in `src/shelfline/tui/widgets.py`.

Responsibilities:

- Render folder details.
- Render book details.
- Contain `CoverDisplay` in a constrained area.
- Render acquisition rows.
- Refresh when selected entry changes.

`CoverDisplay` should stay reusable, but its catalog usage must be constrained by container/style rather than allowed to occupy unbounded vertical space.

### Services

Keep cover fetching in `CatalogWorkflow`.

No new persistence model is required. Catalog preview covers can continue to use the existing cover cache directory under the configured library path.

## Styling

Add CSS classes for:

- Catalog details pane.
- Cover container.
- Book metadata rows.
- Description body.
- Acquisition list inside the pane.

The cover container should have stable dimensions and should not push all book metadata off screen. The details pane should scroll if the description is long.

## Error Handling

- Cover fetch failure must not block catalog browsing.
- Failed cover fetch leaves text fallback visible.
- Download errors continue to use existing download status behavior.
- If no workflow is wired, `d` reports that download workflow is unavailable.
- If no acquisition exists, `d` reports that no acquisition is available.

## Testing

Add or update tests for:

- Feed screen renders a right-hand detail pane for the selected book.
- Moving selection updates the detail pane.
- Folder rows show folder-specific details and no author/cover/download noise.
- `d` downloads the selected book's default acquisition.
- `d` on a folder reports no downloads.
- Cover fetch updates the selected book pane with a cached path.
- Selection changes clear stale cover data.
- Existing catalog navigation tests continue to pass.

## Out Of Scope

- Full acquisition-row keyboard focus inside the detail pane.
- New cover aspect-ratio controls in config.
- A separate image resizing pipeline.
- PDF/CBR/CBZ reader improvements.
- Library screen redesign.

## Acceptance Criteria

- Catalog browsing no longer opens a full-page book detail screen for normal book inspection.
- Selected book details and download options are visible in the catalog screen's right pane.
- Cover images are visibly constrained and do not cover the description.
- `d` downloads the selected book from the catalog feed screen.
- Folder rows remain navigable with `Enter`.
- Full test suite passes.
