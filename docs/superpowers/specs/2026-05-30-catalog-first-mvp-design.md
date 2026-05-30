# Catalog-First MVP Design

## Goal

Build a Python terminal UI for browsing OPDS 1.x catalogs, downloading one book at a time into a user-configured library path, tracking downloaded books locally, and previewing EPUB text inside the terminal. The MVP should create a solid catalog and library foundation for later in-terminal readers for PDF, DjVu, CBR, and other formats.

## Scope

Included in the MVP:

- Python + Textual/Rich TUI.
- OPDS 1.x Atom catalog browsing.
- Optional Basic Authentication per OPDS catalog.
- Saved catalog list.
- Single active download workflow.
- User-configured library path required before downloads.
- SQLite-backed local state.
- EPUB text preview for downloaded EPUB files.
- Metadata tracking for downloaded non-EPUB files.

Explicitly out of scope for the MVP:

- OPDS 2.x JSON feeds.
- Multiple simultaneous downloads.
- PDF, DjVu, CBR, CBZ, or other in-terminal rendering.
- Full-text book search.
- Sync, annotations, reading progress persistence, and advanced library management.
- OAuth, bearer token, cookie, or custom authentication flows.

## Architecture

The app is organized into layered modules. Textual screens call services in the core modules, and core modules do not depend on Textual.

- `tui`: Textual screens, widgets, commands, key bindings, and status display.
- `catalog`: OPDS fetching, Basic Auth handling, feed parsing, URL resolution, and normalized catalog models.
- `downloads`: single-download orchestration, progress reporting, temporary file handling, retries, and final file placement.
- `library`: SQLite schema, settings, saved catalogs, downloaded book metadata, and feed cache.
- `reader`: EPUB text extraction and preview document model.
- `config`: first-run and startup configuration, especially library path validation.

Network fetches and downloads run in Textual workers so the interface remains responsive. OPDS parsing, download logic, library persistence, and EPUB extraction should be testable without launching the TUI.

## TUI Shape

The app uses a practical two-pane layout:

- Left/sidebar: saved catalogs, current feed trail, and library shortcut.
- Main pane: current feed entries or downloaded books.
- Details/footer area: selected item metadata, available actions, download state, and errors.

MVP screens:

- `SetupScreen`: choose and validate the user-configured library path.
- `CatalogsScreen`: list saved catalogs and add a new OPDS catalog.
- `CatalogAuthScreen` or modal: optional Basic Auth username/password when adding or editing a catalog.
- `FeedScreen`: browse OPDS navigation/acquisition feeds with breadcrumb and back stack.
- `EntryScreen`: show item details and acquisition/download options.
- `DownloadStatus`: modal or bottom panel for the single active download.
- `LibraryScreen`: show downloaded items and stored metadata.
- `EpubPreviewScreen`: scrollable plain-text preview for downloaded EPUBs.

Keyboard-first bindings:

- Arrow keys or `j`/`k`: move selection.
- `Enter`: open selected catalog/feed/item.
- `d`: download selected acquisition item.
- `b`: back.
- `/`: filter the visible list.
- `r`: refresh current feed.
- `l`: open library.
- `q`: quit or close current screen.

## Core Flow

On first launch, if no library path is configured, the app asks for one and validates that it exists or can be created. After setup, the user lands in the catalog area.

Primary flow:

1. Add or select an OPDS 1.x catalog URL.
2. Optionally attach Basic Auth credentials to the catalog.
3. Fetch the feed and display entries.
4. Navigate OPDS navigation links like folders.
5. Open an acquisition entry details view.
6. Choose the best EPUB acquisition link when one is available.
7. Download one book at a time into the configured library path.
8. Save metadata in SQLite.
9. Offer a basic EPUB text preview for EPUB downloads.
10. Track non-EPUB downloads as stored files with metadata, without in-terminal preview.

Recoverable errors:

- Invalid or unreachable catalog URL.
- Authentication required or authentication failed.
- Invalid OPDS feed.
- Missing acquisition links.
- No EPUB acquisition link for EPUB preview.
- Download failure or interruption.
- Duplicate local file.
- Invalid library path.

Errors should show clear messages and preserve a retry/back path.

## OPDS And Authentication

The MVP targets OPDS 1.x Atom feeds. The catalog layer normalizes feedparser output into internal models:

- `CatalogFeed`: feed title, source URL, updated time, entries, and navigation context.
- `CatalogEntry`: title, authors, summary, categories, identifiers, updated time, and links.
- `AcquisitionLink`: URL, relation, media type, title, size if available, and indirect/acquisition metadata where practical.

The parser resolves relative URLs against the feed URL and distinguishes navigation links from acquisition links.

Basic Authentication is supported per saved catalog:

- When adding a catalog, the user can provide no credentials or a username/password.
- Credentials are used for catalog feed requests and acquisition/download requests that belong to that catalog.
- Credentials are never displayed in logs, status messages, exception strings, or exported metadata.
- Catalog URLs containing embedded credentials should be accepted for compatibility, but the app should normalize them into separate credential fields before saving when possible.
- Credential storage starts with local SQLite fields suitable for MVP development, with a clear boundary so it can move to a platform keyring later.

Only HTTP Basic Auth is in scope. Digest auth, OAuth, browser login, cookies, and custom token flows are out of scope.

## Data Model

SQLite stores app state. Downloaded files live under the user-configured library path.

Suggested tables:

- `settings`: library path and small app preferences.
- `catalogs`: name, URL, optional Basic Auth username/password, last fetched time, and last error.
- `feed_cache`: feed URL, catalog ID, title, fetched timestamp, and raw or normalized feed cache.
- `books`: title, authors, identifiers, source catalog ID, source entry URL, acquisition URL, media type, local file path, and download timestamp.

Credential fields should be isolated behind a repository or credential store interface. This keeps the MVP simple while leaving room to replace SQLite credential storage with OS keyring integration later.

Downloads write to a temporary file first, then move to the final library location only after completion and basic validation. Interrupted downloads must not appear as complete library books.

## Reader

The MVP reader previews EPUB text only. It accepts a local EPUB path and returns a document outline plus text sections for the TUI to render. It does not own library metadata or download state.

Reader behavior:

- Extract readable chapter text from EPUB spine order.
- Show title/chapter headings when available.
- Render plain text in a scrollable Textual view.
- Fail gracefully for malformed or unsupported EPUBs.

Non-EPUB formats are tracked in the library but display a message that in-terminal preview is not implemented yet.

## Testing

Core tests:

- OPDS parser fixtures for navigation feeds, acquisition feeds, missing fields, relative URLs, and invalid XML.
- Basic Auth fetch tests that verify credentials are sent when configured and omitted when not configured.
- Credential redaction tests for logs/errors/status messages.
- Download tests with mocked HTTP responses, including success, interruption, failure, and duplicate filenames.
- Library tests using temporary SQLite databases and temporary library directories.
- EPUB preview tests with a tiny fixture EPUB.

TUI smoke tests:

- Startup with missing library path opens setup.
- Setup path validation accepts a valid path and rejects an invalid one.
- Saved catalogs render in the catalog screen.
- Authenticated catalog failures produce a recoverable error.
- Feed entries render after a mocked successful fetch.
- Library screen shows downloaded items.

## Implementation Notes

Recommended dependencies:

- `textual` for the TUI.
- `rich` for terminal text rendering.
- `httpx` for HTTP fetching and streaming downloads.
- `feedparser` for OPDS 1.x Atom parsing.
- `sqlite3` from the standard library for MVP persistence.
- An EPUB parsing library such as `ebooklib`, or a small EPUB ZIP/XML extractor if dependency weight becomes an issue.

Dependency choices should be confirmed during implementation planning against current package health and local project constraints.

## Future Extensions

Likely next phases:

- OPDS 2.x JSON support.
- Keyring-backed credential storage.
- Download queue.
- PDF preview using a terminal-friendly text/image strategy.
- DjVu and comic archive support.
- Reading progress and bookmarks.
- Library search and filtering.
- Catalog search support where OPDS feeds expose search links.
