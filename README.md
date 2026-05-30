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
