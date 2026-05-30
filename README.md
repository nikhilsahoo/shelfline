# epub-tui

Catalog-first terminal app for browsing OPDS 1.x catalogs, downloading books, and previewing EPUB text.

## Development

```powershell
python -m pip install -e ".[dev]"
python -m pytest -v
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
