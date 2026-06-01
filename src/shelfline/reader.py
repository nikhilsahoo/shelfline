from __future__ import annotations

from dataclasses import dataclass
import html
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
class EpubOutlineItem:
    title: str
    section_index: int


@dataclass(frozen=True)
class EpubPreview:
    title: str
    outline: tuple[EpubOutlineItem, ...]
    sections: tuple[EpubSection, ...]

    @property
    def section_count(self) -> int:
        return len(self.sections)

    def section_at(self, index: int) -> EpubSection:
        if not self.sections:
            raise ReaderError("EPUB preview has no readable text sections")
        return self.sections[self._clamp_section_index(index)]

    def progress_label(self, index: int) -> str:
        if not self.sections:
            raise ReaderError("EPUB preview has no readable text sections")
        section_number = self._clamp_section_index(index) + 1
        return f"{section_number} / {self.section_count}"

    def next_section_index(self, index: int) -> int:
        return self._clamp_section_index(self._clamp_section_index(index) + 1)

    def previous_section_index(self, index: int) -> int:
        return self._clamp_section_index(self._clamp_section_index(index) - 1)

    def _clamp_section_index(self, index: int) -> int:
        if not self.sections:
            return 0
        return max(0, min(index, self.section_count - 1))


class ReaderError(RuntimeError):
    """Raised when an EPUB cannot be converted into a text preview."""


_STRUCTURAL_LABEL_TOKENS = {
    "contents",
    "copyright",
    "cover",
    "guide",
    "landmark",
    "landmarks",
    "nav",
    "navigation",
    "titlepage",
    "toc",
}
_STRUCTURAL_LABEL_PHRASES = ("table of contents", "title page")
_TITLEPAGE_LIKE_STRUCTURAL_TOKENS = {"copyright", "cover", "titlepage"}
_TITLEPAGE_LIKE_STRUCTURAL_PHRASES = ("title page",)


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
        if self._active_heading is not None:
            self._heading_parts.append(data)
            return
        self._parts.append(data)


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
    outline = tuple(
        EpubOutlineItem(title=section.heading, section_index=index)
        for index, section in enumerate(sections)
    )
    return EpubPreview(title=title, outline=outline, sections=sections)


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
        if section is not None and not _is_structural_document_item(item, section):
            sections.append(section)

    return sections


def _spine_items(book: epub.EpubBook) -> list[Any]:
    items: list[Any] = []
    for entry in book.spine:
        item = _item_from_spine_entry(book, entry)
        if item is not None and _is_document_item(item):
            items.append(item)
    return items


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


def _is_structural_document_item(item: Any, section: EpubSection) -> bool:
    if _has_titlepage_like_structural_label(item, section):
        return _looks_like_titlepage_text(section.text)
    return _has_structural_label(item, section) and _looks_like_navigation_text(section.text)


def _has_structural_label(item: Any, section: EpubSection) -> bool:
    for value in _item_label_values(item, section):
        label = _normalize_label(value)
        if not label:
            continue
        if any(phrase in label for phrase in _STRUCTURAL_LABEL_PHRASES):
            return True
        if set(re.findall(r"[a-z0-9]+", label)) & _STRUCTURAL_LABEL_TOKENS:
            return True
    return False


def _has_titlepage_like_structural_label(item: Any, section: EpubSection) -> bool:
    for value in _item_label_values(item, section):
        label = _normalize_label(value)
        if not label:
            continue
        if any(phrase in label for phrase in _TITLEPAGE_LIKE_STRUCTURAL_PHRASES):
            return True
        if set(re.findall(r"[a-z0-9]+", label)) & _TITLEPAGE_LIKE_STRUCTURAL_TOKENS:
            return True
    return False


def _item_label_values(item: Any, section: EpubSection) -> list[str]:
    values = []
    for attribute in ("id", "file_name", "title"):
        value = getattr(item, attribute, None)
        if value:
            values.append(str(value))
    name = getattr(item, "get_name", lambda: "")()
    if name:
        values.append(str(name))
    item_id = getattr(item, "get_id", lambda: "")()
    if item_id:
        values.append(str(item_id))
    return values


def _looks_like_navigation_text(text: str) -> bool:
    lines = [line for line in (_normalize_inline_text(line) for line in text.splitlines()) if line]
    if len(lines) < 3:
        return False

    short_lines = sum(len(line) <= 48 for line in lines)
    compact_lines = sum(len(re.findall(r"\w+", line)) <= 8 for line in lines)
    prose_lines = sum(bool(re.search(r"[.!?;:]$", line)) for line in lines)
    line_count = len(lines)

    return (
        short_lines / line_count >= 0.75
        and compact_lines / line_count >= 0.75
        and prose_lines / line_count <= 0.4
    )


def _looks_like_titlepage_text(text: str) -> bool:
    lines = [line for line in (_normalize_inline_text(line) for line in text.splitlines()) if line]
    if not lines:
        return False

    word_count = len(re.findall(r"\w+", " ".join(lines)))
    short_lines = sum(len(line) <= 80 for line in lines)
    compact_lines = sum(len(re.findall(r"\w+", line)) <= 12 for line in lines)

    return (
        word_count <= 80
        and short_lines == len(lines)
        and compact_lines / len(lines) >= 0.8
    )


def _normalize_label(value: str) -> str:
    label = value.casefold()
    label = re.sub(r"\.[a-z0-9]+$", "", label)
    label = re.sub(r"[/\\._-]+", " ", label)
    return _normalize_inline_text(label)


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
    text = html.unescape(text)
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/\s*p\s*>", "\n\n", text, flags=re.IGNORECASE)
    lines = [_normalize_inline_text(line) for line in text.splitlines()]
    return "\n\n".join(line for line in lines if line)
