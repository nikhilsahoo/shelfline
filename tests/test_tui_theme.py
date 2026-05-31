from __future__ import annotations

from epub_tui.tui.theme import (
    BASIC_AUTH_LABEL,
    BOOK_LABEL,
    DOWNLOADS_LABEL,
    ENTRY_LABEL,
    FOLDER_LABEL,
    LOCAL_PATH_LABEL,
    NO_AUTH_LABEL,
    OPEN_PREVIEW_LABEL,
    READ_LABEL,
    UNREAD_LABEL,
)


def test_semantic_labels_use_terminal_friendly_glyphs() -> None:
    assert FOLDER_LABEL.text == "▣ Folder"
    assert BOOK_LABEL.text == "▤ Book"
    assert ENTRY_LABEL.text == "• Entry"
    assert READ_LABEL.text == "✓ Read"
    assert UNREAD_LABEL.text == "○ Unread"
    assert BASIC_AUTH_LABEL.text == "◈ Basic auth"
    assert NO_AUTH_LABEL.text == "- No auth"
    assert DOWNLOADS_LABEL.text == "↓ Downloads"
    assert LOCAL_PATH_LABEL.text == "⌂ Local path"
    assert OPEN_PREVIEW_LABEL.text == "↵ Open/preview"
