from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any

from ebooklib import ITEM_DOCUMENT, epub


@dataclass(frozen=True)
class EpubSection:
    heading: str
    text: str


@dataclass(frozen=True)
class EpubPreview:
    title: str
    sections: tuple[EpubSection, ...]


class ReaderError(RuntimeError):
    """Raised when an EPUB cannot be converted into a text preview."""


class _HtmlTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "div",
        "dl",
        "dt",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._headings: dict[str, str] = {}
        self._active_heading: str | None = None
        self._heading_parts: list[str] = []
        self._ignored_depth = 0

    @property
    def text(self) -> str:
        return _normalize_block_text("".join(self._parts))

    @property
    def heading(self) -> str | None:
        for tag in ("h1", "h2", "h3"):
            heading = self._headings.get(tag)
            if heading:
                return heading
        return None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style"}:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")
        if tag in {"h1", "h2", "h3"}:
            self._active_heading = tag
            self._heading_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style"} and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag == self._active_heading:
            heading = _normalize_inline_text("".join(self._heading_parts))
            if heading and tag not in self._headings:
                self._headings[tag] = heading
            self._active_heading = None
            self._heading_parts = []
        if tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        self._parts.append(data)
        if self._active_heading is not None:
            self._heading_parts.append(data)


def extract_epub_preview(path: Path) -> EpubPreview:
    epub_path = Path(path)
    try:
        book = epub.read_epub(str(epub_path))
    except Exception as exc:
        raise ReaderError(f"Could not read EPUB preview from {epub_path}: {exc}") from exc

    try:
        title = _book_title(book, epub_path)
        sections = tuple(_iter_text_sections(book))
    except ReaderError:
        raise
    except Exception as exc:
        raise ReaderError(f"Could not extract EPUB preview from {epub_path}: {exc}") from exc

    if not sections:
        raise ReaderError(f"No readable text sections found in {epub_path}")
    return EpubPreview(title=title, sections=sections)


def _book_title(book: epub.EpubBook, path: Path) -> str:
    metadata = book.get_metadata("DC", "title")
    for value, _attributes in metadata:
        title = _normalize_inline_text(str(value))
        if title:
            return title
    return path.stem


def _iter_text_sections(book: epub.EpubBook) -> list[EpubSection]:
    sections: list[EpubSection] = []
    seen_ids: set[int] = set()

    for item in _spine_items(book):
        marker = id(item)
        if marker in seen_ids:
            continue
        seen_ids.add(marker)
        section = _section_from_item(item)
        if section is not None:
            sections.append(section)

    return sections


def _spine_items(book: epub.EpubBook) -> list[Any]:
    items: list[Any] = []
    for entry in book.spine:
        item = _item_from_spine_entry(book, entry)
        if item is not None and _is_document_item(item):
            items.append(item)
    if items:
        return items
    return [item for item in book.get_items() if _is_document_item(item)]


def _item_from_spine_entry(book: epub.EpubBook, entry: Any) -> Any | None:
    if hasattr(entry, "get_content"):
        return entry

    item_id = entry[0] if isinstance(entry, tuple) else entry
    if not isinstance(item_id, str):
        return None
    if item_id == "nav":
        return None
    return book.get_item_with_id(item_id)


def _is_document_item(item: Any) -> bool:
    return getattr(item, "get_type", lambda: None)() == ITEM_DOCUMENT


def _section_from_item(item: Any) -> EpubSection | None:
    content = item.get_content()
    if isinstance(content, bytes):
        html = content.decode("utf-8", errors="replace")
    else:
        html = str(content)

    parser = _HtmlTextExtractor()
    parser.feed(html)
    parser.close()

    text = parser.text
    if not text:
        return None

    heading = parser.heading or _item_title(item)
    return EpubSection(heading=heading, text=text)


def _item_title(item: Any) -> str:
    for attribute in ("title", "file_name", "id"):
        value = getattr(item, attribute, None)
        if value:
            return _normalize_inline_text(str(value))
    name = getattr(item, "get_name", lambda: "")()
    return _normalize_inline_text(str(name)) or "Untitled section"


def _normalize_inline_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _normalize_block_text(text: str) -> str:
    lines = [_normalize_inline_text(line) for line in text.splitlines()]
    return "\n\n".join(line for line in lines if line)
