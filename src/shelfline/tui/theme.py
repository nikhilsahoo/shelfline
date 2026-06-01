from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticLabel:
    text: str
    css_class: str


FOLDER_LABEL = SemanticLabel("▣ Folder", "kind-folder")
BOOK_LABEL = SemanticLabel("▤ Book", "kind-book")
ENTRY_LABEL = SemanticLabel("• Entry", "kind-entry")
BASIC_AUTH_LABEL = SemanticLabel("◈ Basic auth", "auth-basic")
NO_AUTH_LABEL = SemanticLabel("- No auth", "auth-none")
READ_LABEL = SemanticLabel("✓ Read", "state-read")
UNREAD_LABEL = SemanticLabel("○ Unread", "state-unread")
DOWNLOADS_LABEL = SemanticLabel("↓ Downloads", "action-downloads")
LOCAL_PATH_LABEL = SemanticLabel("⌂ Local path", "field-local-path")
OPEN_PREVIEW_LABEL = SemanticLabel("↵ Open/preview", "action-open-preview")
ERROR_LABEL = SemanticLabel("Error", "state-error")
SUCCESS_LABEL = SemanticLabel("Ready", "state-success")
WARNING_LABEL = SemanticLabel("Warning", "state-warning")


def labeled(label: SemanticLabel, value: object | None = None, *, separator: str = " ") -> str:
    if value is None:
        return label.text
    return f"{label.text}{separator}{value}"


def glyph(label: SemanticLabel) -> str:
    return label.text.split(" ", 1)[0]


def read_status_label(is_read: bool) -> SemanticLabel:
    return READ_LABEL if is_read else UNREAD_LABEL
