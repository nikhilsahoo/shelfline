from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SemanticLabel:
    text: str
    css_class: str


FOLDER_LABEL = SemanticLabel("[Folder]", "kind-folder")
BOOK_LABEL = SemanticLabel("[Book]", "kind-book")
ENTRY_LABEL = SemanticLabel("[Entry]", "kind-entry")
ERROR_LABEL = SemanticLabel("Error", "state-error")
SUCCESS_LABEL = SemanticLabel("Ready", "state-success")
WARNING_LABEL = SemanticLabel("Warning", "state-warning")
