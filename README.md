# epub-tui

Catalog-first terminal app for browsing OPDS 1.x catalogs, downloading books, and previewing EPUB text.

## Development

Windows PowerShell:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -v
python -m epub_tui --help
```

Linux shell:

```shell
python -m pip install -e '.[dev]'
python -m pytest -v
python -m epub_tui --help
```

Run the app from an editable checkout with either the console script or module entrypoint:

```powershell
epub-tui
python -m epub_tui
```

Use `--config` to point at a specific JSON config file:

```powershell
python -m epub_tui --config .\config.json
epub-tui --config C:\Users\you\AppData\Roaming\epub-tui\config.json
```

Without `--config`, epub-tui looks for a config file at:

- Windows: `%APPDATA%\epub-tui\config.json`
- Linux/macOS with `XDG_CONFIG_HOME`: `$XDG_CONFIG_HOME/epub-tui/config.json`
- Linux/macOS fallback: `~/.config/epub-tui/config.json`

If the config file is missing, the app opens the setup screen.

Release verification should run the full test suite and `python -m epub_tui --help` on both Windows and Linux.

## Usage

On first run, enter an existing library/download directory. The app stores its JSON config at the default platform path unless `--config` is provided.

From the catalog screen, add OPDS catalogs with `a` or the `New catalog` button. Catalogs may include Basic Auth credentials either in the JSON config or through the TUI add-catalog form.

Common keys:

- `c`: show catalogs
- `a`: add a catalog
- `l`: show library
- `j` / `down`: move selection down
- `k` / `up`: move selection up
- `enter`: open selected item
- `b`: go back from feed/download screens
- `d`: download the selected acquisition from an entry screen
- `m`: mark a library book read/unread
- `x`: delete a library book
- `r`: refresh the library
- `q`: quit

Catalog feeds show breadcrumbs for nested OPDS folders and label rows as `[Folder]`, `[Book]`, or `[Entry]`. Download status screens show progress where the server reports a content length and an indeterminate byte counter otherwise.

## MVP 2 Usage

MVP 2 adds a polished Textual shell, searchable library, scrollable EPUB reader, reading progress, bookmarks, and keyring-backed Basic Auth password storage where available.

Library search:

- `l`: open the local library.
- `/`: focus the library search box.
- `enter`: apply the current search while the search box is active, or open the selected book otherwise.
- `j` / `down`: move to the next book.
- `k` / `up`: move to the previous book.
- `r`: refresh the library, preserving the current search when one is active.
- `m`: mark the selected book read/unread.
- `x`: delete the selected book and clear its saved progress/bookmarks.

Library rows show title, authors, read state, media type, source catalog, and local file path. Search matches downloaded book titles and authors from the local SQLite library metadata.

EPUB reader keys:

- `n`: next EPUB section.
- `p`: previous EPUB section.
- `m`: add a bookmark at the current section, or remove an existing bookmark at the same section and position.
- `b`: back to the previous screen.
- `c`: show catalogs.
- `l`: show library.
- `q`: quit.

Opening a downloaded EPUB from the library starts the reader. When the reader moves between sections with `n` or `p`, epub-tui saves reading progress to the local SQLite state database. Reopening the same library-backed EPUB resumes at the saved section. If progress cannot be loaded or saved, the reader keeps working and shows a recoverable status message.

Bookmarks are local-only. Pressing `m` in the reader adds a bookmark labeled with the current section heading. Pressing `m` again at the same section and position removes the existing bookmark.

### Credentials

Catalog metadata remains in JSON. Basic Auth usernames remain visible in JSON, while passwords can be stored in the OS keyring where available. JSON `auth.password` remains supported as an explicit fallback for editable config files, headless environments, and portable setups where keyring access is unavailable.

Use `password_ref` to point at a keyring service/reference:

```json
{
  "library_path": "C:/Users/you/Books/epub-tui",
  "catalogs": [
    {
      "name": "Private Library",
      "url": "https://library.example.test/opds",
      "auth": {
        "username": "reader@example.test",
        "password_ref": "epub-tui:Private%20Library"
      }
    }
  ],
  "preferences": {}
}
```

The JSON fallback remains valid:

```json
{
  "auth": {
    "username": "reader@example.test",
    "password": "change-me"
  }
}
```

Example config:

```json
{
  "library_path": "C:/Users/you/Books/epub-tui",
  "catalogs": [
    {
      "name": "Public OPDS",
      "url": "https://example.test/opds"
    },
    {
      "name": "Private Library",
      "url": "https://library.example.test/opds",
      "auth": {
        "username": "reader@example.test",
        "password": "change-me"
      }
    }
  ],
  "preferences": {}
}
```

## Manual Smoke Checklist

Before an MVP 2 release, run the automated checks above and smoke the app manually where an interactive terminal and test OPDS catalog are available:

- First-run setup accepts an existing library/download directory.
- Add OPDS catalog works.
- Browse nested OPDS folders.
- Download an EPUB.
- Open Library.
- Search Library.
- Open an EPUB reader from the library.
- Navigate reader sections with `n` and `p`.
- Close and reopen the EPUB, confirming progress resumes at the saved section.
- Add a bookmark with `m`, then press `m` again at the same section to remove it.
- Trigger a duplicate download error and confirm the error remains visible.
- Basic Auth catalog works with keyring-backed credentials or the documented JSON password fallback.

## MVP 2

- Polished Textual shell for catalog and library screens
- Searchable local library
- Scrollable EPUB reader with section navigation
- Reading progress persistence and resume for library-backed EPUBs
- Local EPUB bookmarks with add/remove toggle behavior
- Keyring-backed Basic Auth password storage where available
- JSON password fallback for editable config and headless portability

## MVP 1 Foundation

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

## Current Limits

- OPDS 2.x is not supported yet.
- OAuth and browser-based authentication are not supported yet.
- PDF, DjVu, CBR, and CBZ are downloaded and tracked but not rendered in the terminal yet.
- Downloads are intentionally single-file, not queued.
- Annotations, sync, and full-text book search are not supported yet.
