from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.widget import Widget
from textual.widgets import Static

from shelfline.catalog.models import AcquisitionLink, CatalogEntry
from shelfline.config import CatalogConfig
from shelfline.downloads import DownloadProgress
from shelfline.library import BookRecord
from shelfline.tui.theme import (
    BASIC_AUTH_LABEL,
    BOOK_LABEL,
    DOWNLOADS_LABEL,
    ENTRY_LABEL,
    FOLDER_LABEL,
    LOCAL_PATH_LABEL,
    NO_AUTH_LABEL,
    OPEN_PREVIEW_LABEL,
    glyph,
    SemanticLabel,
    labeled,
    read_status_label,
)


class BusyIndicator(Static):
    """Small status widget used while a screen waits on outgoing work."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        super().__init__(message, **kwargs)
        self._renderable = message

    @property
    def renderable(self) -> str:
        return self._renderable

    def start(self, message: str) -> None:
        self._renderable = message
        self.update(message)

    def stop(self) -> None:
        self._renderable = ""
        self.update("")


class StatusLine(Static):
    def __init__(self, message: str = "Ready", **kwargs: object) -> None:
        super().__init__(message, **kwargs)
        self._renderable = message

    @property
    def renderable(self) -> str:
        return self._renderable

    def set_message(self, message: str) -> None:
        self._renderable = message
        self.update(message)


class CatalogRow(Container):
    def __init__(
        self,
        catalog: CatalogConfig,
        *,
        index: int,
        selected: bool = False,
        **kwargs: object,
    ) -> None:
        self.catalog = catalog
        self.index = index
        self.selected = selected
        auth_class = "auth-basic" if catalog.auth else "auth-none"
        classes = f"catalog-row {auth_class}"
        if selected:
            classes = f"{classes} selected"
        super().__init__(id=f"catalog-row-{index}", classes=classes, **kwargs)

    @property
    def renderable(self) -> str:
        return self._row_text()

    def compose(self) -> ComposeResult:
        yield Static(">" if self.selected else " ", classes="row-marker")
        yield Static(f"{self.index + 1}.", classes="row-index")
        yield Static(self.catalog.name, classes="row-title")
        yield Static(self.catalog.url, classes="catalog-url")
        yield Static(self.auth_text, classes="catalog-auth")

    @property
    def auth_text(self) -> str:
        return BASIC_AUTH_LABEL.text if self.catalog.auth else NO_AUTH_LABEL.text

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        if selected:
            self.add_class("selected")
        else:
            self.remove_class("selected")
        if self.is_mounted:
            self.query_one(".row-marker", Static).update(">" if selected else " ")

    def update_catalog(self, catalog: CatalogConfig, *, index: int, selected: bool) -> None:
        self.catalog = catalog
        self.index = index
        self.display = True
        self.remove_class("auth-basic")
        self.remove_class("auth-none")
        self.add_class("auth-basic" if catalog.auth else "auth-none")
        self.set_selected(selected)
        if not self.is_mounted:
            return
        self.query_one(".row-index", Static).update(f"{index + 1}.")
        self.query_one(".row-title", Static).update(catalog.name)
        self.query_one(".catalog-url", Static).update(catalog.url)
        self.query_one(".catalog-auth", Static).update(self.auth_text)

    def _row_text(self) -> str:
        return (
            f"{'>' if self.selected else ' '} {self.index + 1}. "
            f"{self.catalog.name} - {self.catalog.url} [{self.auth_text}]"
        )


class CatalogList(VerticalScroll):
    def __init__(
        self,
        catalogs: list[CatalogConfig],
        *,
        selected_index: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__(id="catalog-list", classes="catalog-list", **kwargs)
        self.catalogs = catalogs
        self.selected_index = selected_index

    @property
    def renderable(self) -> str:
        return self.render_text(self.catalogs, self.selected_index)

    def compose(self) -> ComposeResult:
        empty_state = Static(
            f"{glyph(FOLDER_LABEL)} No catalogs configured",
            id="catalog-empty",
            classes="empty-state",
        )
        empty_state.display = not self.catalogs
        yield empty_state
        yield from self._catalog_widgets()

    def set_catalogs(self, catalogs: list[CatalogConfig], selected_index: int) -> None:
        self.catalogs = catalogs
        self.selected_index = selected_index
        self.query_one("#catalog-empty", Static).display = not catalogs
        rows = list(self.query(CatalogRow))
        for index, catalog in enumerate(catalogs):
            selected = index == selected_index
            if index < len(rows):
                rows[index].update_catalog(catalog, index=index, selected=selected)
            else:
                self.mount(CatalogRow(catalog, index=index, selected=selected))
        for row in rows[len(catalogs) :]:
            row.display = False
            row.set_selected(False)

    def set_selected_index(self, selected_index: int) -> None:
        self.selected_index = selected_index
        selected_row: CatalogRow | None = None
        for row in self.query(CatalogRow):
            selected = row.index == selected_index
            row.set_selected(selected)
            if selected:
                selected_row = row
        if selected_row is not None:
            self.scroll_to_widget(selected_row, animate=False, immediate=True)

    def _catalog_widgets(self) -> list[CatalogRow]:
        return [
            CatalogRow(catalog, index=index, selected=index == self.selected_index)
            for index, catalog in enumerate(self.catalogs)
        ]

    @staticmethod
    def render_text(catalogs: list[CatalogConfig], selected_index: int) -> str:
        if not catalogs:
            return f"{glyph(FOLDER_LABEL)} No catalogs configured"
        return "\n".join(
            CatalogRow(catalog, index=index, selected=index == selected_index).renderable
            for index, catalog in enumerate(catalogs)
        )


class CatalogEntryRow(Container):
    def __init__(
        self,
        entry: CatalogEntry,
        *,
        index: int,
        selected: bool = False,
        **kwargs: object,
    ) -> None:
        self.entry = entry
        self.index = index
        self.selected = selected
        classes = f"feed-entry-row {self.kind_class}"
        if selected:
            classes = f"{classes} selected"
        super().__init__(id=f"feed-entry-{index}", classes=classes, **kwargs)

    @property
    def kind(self) -> str:
        return self._kind_label().text.split(" ", 1)[-1]

    @property
    def kind_label(self) -> str:
        return self._kind_label().text

    def _kind_label(self) -> SemanticLabel:
        if self.entry.navigation_url is not None:
            return FOLDER_LABEL
        if self.entry.acquisition_links:
            return BOOK_LABEL
        return ENTRY_LABEL

    @property
    def kind_class(self) -> str:
        return self._kind_label().css_class

    @property
    def renderable(self) -> str:
        return self._row_text()

    def compose(self) -> ComposeResult:
        yield Static(">" if self.selected else " ", classes="row-marker")
        yield Static(f"{self.index + 1}.", classes="row-index")
        yield Static(self.kind_label, classes="row-kind")
        yield Static(self.entry.title, classes="row-title")
        yield Static(self._meta_text(), classes="row-meta")

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        if selected:
            self.add_class("selected")
        else:
            self.remove_class("selected")
        if self.is_mounted:
            self.query_one(".row-marker", Static).update(">" if selected else " ")

    def _meta_text(self) -> str:
        if self.entry.navigation_url is not None:
            return self.entry.updated or "Browse catalog"
        if self.entry.authors:
            return ", ".join(self.entry.authors)
        if self.entry.acquisition_links:
            return "Unknown author"
        return self.entry.updated or ""

    def _row_text(self) -> str:
        label = f"{self.kind_label} {self.entry.title}"
        meta = self._meta_text()
        if meta:
            label = f"{label} - {meta}"
        return f"{'>' if self.selected else ' '} {self.index + 1}. {label}"


class FeedEntryList(VerticalScroll):
    def __init__(
        self,
        *,
        breadcrumbs: list[str],
        source_url: str,
        updated: str | None,
        entries: list[CatalogEntry],
        selected_index: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__(id="feed-body", classes="feed-entry-list", **kwargs)
        self.breadcrumbs = breadcrumbs
        self.source_url = source_url
        self.updated = updated
        self.entries = entries
        self.selected_index = selected_index

    @property
    def renderable(self) -> str:
        return self.render_text(
            self.breadcrumbs,
            self.source_url,
            self.updated,
            self.entries,
            self.selected_index,
        )

    def compose(self) -> ComposeResult:
        yield Static(" > ".join(self.breadcrumbs), id="feed-breadcrumbs", classes="feed-breadcrumbs")
        yield Static(self.source_url, id="feed-source", classes="feed-source")
        if self.updated:
            yield Static(f"Updated: {self.updated}", id="feed-updated", classes="feed-updated")
        if not self.entries:
            yield Static(f"{glyph(ENTRY_LABEL)} No entries", classes="empty-state")
            return
        for index, entry in enumerate(self.entries):
            yield CatalogEntryRow(
                entry,
                index=index,
                selected=index == self.selected_index,
            )

    def set_selected_index(self, selected_index: int) -> None:
        self.selected_index = selected_index
        selected_row: CatalogEntryRow | None = None
        for row in self.query(CatalogEntryRow):
            selected = row.index == selected_index
            row.set_selected(selected)
            if selected:
                selected_row = row
        if selected_row is not None:
            self.scroll_to_widget(selected_row, animate=False, immediate=True)

    @staticmethod
    def render_text(
        breadcrumbs: list[str],
        source_url: str,
        updated: str | None,
        entries: list[CatalogEntry],
        selected_index: int,
    ) -> str:
        lines = [" > ".join(breadcrumbs), source_url]
        if updated:
            lines.append(f"Updated: {updated}")
        if not entries:
            lines.append(f"{glyph(ENTRY_LABEL)} No entries")
            return "\n".join(lines)
        for index, entry in enumerate(entries):
            lines.append(CatalogEntryRow(entry, index=index, selected=index == selected_index).renderable)
        return "\n".join(lines)


class _OpdsHtmlTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "br":
            self._line_break()
        elif tag in {"p", "div", "section", "article"}:
            self._paragraph_break()
        elif tag == "li":
            self._line_break()
            self._parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"p", "div", "section", "article", "li"}:
            self._paragraph_break()

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)

    def _line_break(self) -> None:
        if self._parts and not self._parts[-1].endswith("\n"):
            self._parts.append("\n")

    def _paragraph_break(self) -> None:
        text = "".join(self._parts)
        if text.strip() and not text.endswith("\n\n"):
            self._parts.append("\n\n")


def clean_opds_html_text(text: str) -> str:
    """Return readable plain text for OPDS summaries that may contain escaped HTML."""

    unescaped = text
    for _ in range(3):
        next_value = html.unescape(unescaped)
        if next_value == unescaped:
            break
        unescaped = next_value

    parser = _OpdsHtmlTextParser()
    parser.feed(unescaped)
    parser.close()
    parsed = parser.text()

    lines: list[str] = []
    previous_blank = True
    for line in parsed.splitlines():
        cleaned = re.sub(r"[ \t]+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
            previous_blank = False
        elif not previous_blank:
            lines.append("")
            previous_blank = True

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


class AcquisitionRow(Container):
    def __init__(
        self,
        link: AcquisitionLink,
        *,
        index: int,
        selected: bool = False,
        **kwargs: object,
    ) -> None:
        self.link = link
        self.index = index
        self.selected = selected
        classes = "acquisition-row"
        if selected:
            classes = f"{classes} selected"
        super().__init__(id=f"acquisition-{index}", classes=classes, **kwargs)

    @property
    def renderable(self) -> str:
        marker = ">" if self.selected else " "
        return f"{marker} {glyph(DOWNLOADS_LABEL)} {self.label} - {self.metadata}"

    @property
    def label(self) -> str:
        return self.link.title or _format_from_media_type(self.link.media_type)

    @property
    def metadata(self) -> str:
        parts = [self.link.media_type]
        if self.link.size is not None:
            parts.append(_format_size(self.link.size))
        return " | ".join(parts)

    def compose(self) -> ComposeResult:
        yield Static(">" if self.selected else " ", classes="row-marker")
        yield Static(f"{self.index + 1}.", classes="row-index")
        yield Static(f"{glyph(DOWNLOADS_LABEL)} {self.label}", classes="acquisition-label")
        yield Static(self.metadata, classes="acquisition-meta")

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        if selected:
            self.add_class("selected")
        else:
            self.remove_class("selected")
        if self.is_mounted:
            self.query_one(".row-marker", Static).update(">" if selected else " ")


class EntryDetailView(VerticalScroll):
    def __init__(
        self,
        entry: CatalogEntry,
        *,
        selected_index: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__(id="entry-body", classes="entry-detail", **kwargs)
        self.entry = entry
        self.selected_index = selected_index

    @property
    def renderable(self) -> str:
        return self.render_text(self.entry, self.selected_index)

    def compose(self) -> ComposeResult:
        yield Static(self.entry.title, classes="entry-title")
        yield Static(self._authors_text(), classes="entry-authors")
        if self.entry.updated:
            yield Static(f"Updated: {self.entry.updated}", classes="entry-updated")

        summary = self.cleaned_summary
        if summary:
            yield Static("Description", classes="entry-section-title")
            yield Static(summary, classes="entry-summary")

        yield Static(DOWNLOADS_LABEL.text, classes="entry-section-title")
        if not self.entry.acquisition_links:
            yield Static("No acquisition links", classes="empty-state")
            return
        for index, link in enumerate(self.entry.acquisition_links):
            yield AcquisitionRow(link, index=index, selected=index == self.selected_index)

    @property
    def cleaned_summary(self) -> str:
        return clean_opds_html_text(self.entry.summary or "")

    def set_selected_index(self, selected_index: int) -> None:
        self.selected_index = selected_index
        selected_row: AcquisitionRow | None = None
        for row in self.query(AcquisitionRow):
            selected = row.index == selected_index
            row.set_selected(selected)
            if selected:
                selected_row = row
        if selected_row is not None:
            self.scroll_to_widget(selected_row, animate=False, immediate=True)

    def _authors_text(self) -> str:
        return ", ".join(self.entry.authors) if self.entry.authors else "Unknown author"

    @staticmethod
    def render_text(entry: CatalogEntry, selected_index: int) -> str:
        lines = [entry.title]
        lines.append(", ".join(entry.authors) if entry.authors else "Unknown author")
        if entry.updated:
            lines.append(f"Updated: {entry.updated}")
        summary = clean_opds_html_text(entry.summary or "")
        if summary:
            lines.extend(["Description:", summary])
        if not entry.acquisition_links:
            lines.append("No acquisition links")
            return "\n".join(lines)

        lines.append(f"{DOWNLOADS_LABEL.text}:")
        for index, link in enumerate(entry.acquisition_links):
            lines.append(AcquisitionRow(link, index=index, selected=index == selected_index).renderable)
        return "\n".join(lines)


def _format_from_media_type(media_type: str) -> str:
    if "epub" in media_type:
        return "EPUB"
    if "pdf" in media_type:
        return "PDF"
    suffix = media_type.rsplit("/", 1)[-1]
    return suffix.upper() if suffix else media_type


def _format_size(size: int) -> str:
    units = ["bytes", "KB", "MB", "GB"]
    value = float(size)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    if unit_index == 0:
        return f"{size} bytes"
    return f"{value:.1f} {units[unit_index]}"


class LibraryBookRow(Container):
    def __init__(
        self,
        book: BookRecord,
        *,
        index: int,
        selected: bool = False,
        **kwargs: object,
    ) -> None:
        self.book = book
        self.index = index
        self.selected = selected
        state_class = "state-read" if book.is_read else "state-unread"
        classes = f"library-book-row {state_class}"
        if selected:
            classes = f"{classes} selected"
        super().__init__(id=f"library-book-{index}", classes=classes, **kwargs)

    @property
    def renderable(self) -> str:
        return self._row_text()

    def compose(self) -> ComposeResult:
        yield Static(">" if self.selected else " ", classes="row-marker")
        yield Static(f"{self.index + 1}.", classes="row-index")
        yield Static(self.book.title, classes="row-title")
        yield Static(self._authors_text(), classes="row-meta")
        yield Static(self._metadata_text(), classes="row-metadata")
        yield Static(labeled(LOCAL_PATH_LABEL, self.book.local_file_path, separator=": "), classes="row-path")

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        if selected:
            self.add_class("selected")
        else:
            self.remove_class("selected")
        if self.is_mounted:
            self.query_one(".row-marker", Static).update(">" if selected else " ")

    def update_book(self, book: BookRecord, *, index: int, selected: bool) -> None:
        self.book = book
        self.index = index
        self.display = True
        self.remove_class("state-read")
        self.remove_class("state-unread")
        self.add_class("state-read" if book.is_read else "state-unread")
        self.set_selected(selected)
        if not self.is_mounted:
            return
        self.query_one(".row-index", Static).update(f"{index + 1}.")
        self.query_one(".row-title", Static).update(book.title)
        self.query_one(".row-meta", Static).update(self._authors_text())
        self.query_one(".row-metadata", Static).update(self._metadata_text())
        self.query_one(".row-path", Static).update(
            labeled(LOCAL_PATH_LABEL, book.local_file_path, separator=": ")
        )

    def _authors_text(self) -> str:
        return ", ".join(self.book.authors) if self.book.authors else "Unknown author"

    def _read_text(self) -> str:
        return read_status_label(self.book.is_read).text

    def _progress_text(self) -> str:
        return "Finished" if self.book.is_read else "Not started"

    def _metadata_text(self) -> str:
        return (
            f"{self._read_text()} | {self._progress_text()} | "
            f"{self.book.media_type} | {self.book.source_catalog}"
        )

    def _row_text(self) -> str:
        return (
            f"{'>' if self.selected else ' '} {self.index + 1}. "
            f"{self.book.title} - {self._authors_text()} [{self._read_text()}] "
            f"{self.book.media_type} | {self.book.source_catalog}\n"
            f"  {labeled(LOCAL_PATH_LABEL, self.book.local_file_path, separator=': ')}"
        )


class LibraryBookList(VerticalScroll):
    def __init__(
        self,
        books: list[BookRecord],
        *,
        selected_index: int = 0,
        **kwargs: object,
    ) -> None:
        super().__init__(id="library-body", classes="library-book-list", **kwargs)
        self.books = books
        self.selected_index = selected_index

    @property
    def renderable(self) -> str:
        return self.render_text(self.books, self.selected_index)

    def compose(self) -> ComposeResult:
        empty_state = Static(
            f"{glyph(BOOK_LABEL)} No downloaded books",
            id="library-empty",
            classes="empty-state",
        )
        empty_state.display = not self.books
        yield empty_state
        yield from self._book_widgets()

    def set_books(self, books: list[BookRecord], selected_index: int) -> None:
        self.books = books
        self.selected_index = selected_index
        self.query_one("#library-empty", Static).display = not books
        rows = list(self.query(LibraryBookRow))
        for index, book in enumerate(books):
            selected = index == selected_index
            if index < len(rows):
                rows[index].update_book(book, index=index, selected=selected)
            else:
                self.mount(LibraryBookRow(book, index=index, selected=selected))
        for row in rows[len(books) :]:
            row.display = False
            row.set_selected(False)

    def set_selected_index(self, selected_index: int) -> None:
        self.selected_index = selected_index
        selected_row: LibraryBookRow | None = None
        for row in self.query(LibraryBookRow):
            selected = row.index == selected_index
            row.set_selected(selected)
            if selected:
                selected_row = row
        if selected_row is not None:
            self.scroll_to_widget(selected_row, animate=False, immediate=True)

    def _book_widgets(self) -> list[Static | LibraryBookRow]:
        return [
            LibraryBookRow(book, index=index, selected=index == self.selected_index)
            for index, book in enumerate(self.books)
        ]

    @staticmethod
    def render_text(books: list[BookRecord], selected_index: int) -> str:
        if not books:
            return f"{glyph(BOOK_LABEL)} No downloaded books"
        return "\n".join(
            LibraryBookRow(book, index=index, selected=index == selected_index).renderable
            for index, book in enumerate(books)
        )


class LibraryDetailView(VerticalScroll):
    def __init__(
        self,
        book: BookRecord | None,
        *,
        status: str = "Ready",
        **kwargs: object,
    ) -> None:
        super().__init__(id="library-detail", classes="library-detail", **kwargs)
        self.book = book
        self.status = status

    @property
    def renderable(self) -> str:
        return self.render_text(self.book, self.status)

    def compose(self) -> ComposeResult:
        for index, line in enumerate(self._lines()):
            yield Static(
                line,
                id=f"library-detail-line-{index}",
                classes=self._line_class(index),
            )

    def set_book(self, book: BookRecord | None) -> None:
        self.book = book
        self._refresh_lines()

    def set_status(self, status: str) -> None:
        self.status = status
        self._refresh_lines()

    def _refresh_lines(self) -> None:
        if not self.is_mounted:
            return
        lines = self._lines()
        existing = list(self.query(Static))
        for index, line in enumerate(lines):
            if index < len(existing):
                existing[index].display = True
                existing[index].update(line)
                existing[index].set_classes(self._line_class(index))
            else:
                self.mount(
                    Static(
                        line,
                        id=f"library-detail-line-{index}",
                        classes=self._line_class(index),
                    )
                )
        for line in existing[len(lines) :]:
            line.display = False

    def _lines(self) -> list[str]:
        return self.render_text(self.book, self.status).splitlines()

    def _line_class(self, index: int) -> str:
        if self.book is None:
            return "empty-state" if index == 0 else "library-detail-meta"
        if index == 0:
            return "entry-title"
        if index in {1, 6}:
            return "library-detail-meta"
        return "library-detail-field"

    @staticmethod
    def render_text(book: BookRecord | None, status: str = "Ready") -> str:
        if book is None:
            return "\n".join(
                [
                    f"{glyph(BOOK_LABEL)} No downloaded books",
                    "Use c to open Catalogs and download books into your library.",
                    f"Status: {status}",
                ]
            )

        authors = ", ".join(book.authors) if book.authors else "Unknown author"
        read_status = read_status_label(book.is_read).text
        return "\n".join(
            [
                book.title,
                authors,
                f"Read status: {read_status}",
                f"Media type: {book.media_type}",
                f"Source catalog: {book.source_catalog}",
                labeled(LOCAL_PATH_LABEL, book.local_file_path, separator=": "),
                f"{OPEN_PREVIEW_LABEL.text}: Enter preview | m read/unread | x delete",
                f"Status: {status}",
            ]
        )


class DownloadProgressDisplay(Static):
    def __init__(self, progress: DownloadProgress | None = None, **kwargs: object) -> None:
        super().__init__("", **kwargs)
        self._renderable = ""
        if progress is None:
            self._set_text("No download active")
        else:
            self.update_progress(progress)

    @property
    def renderable(self) -> str:
        return self._renderable

    def update_progress(self, progress: DownloadProgress) -> None:
        if progress.total_bytes:
            percent = int(progress.percent or 0)
            self._set_text(f"{percent}% ({progress.bytes_received}/{progress.total_bytes} bytes)")
            return

        self._set_text(f"{progress.bytes_received} bytes received (indeterminate)")

    def _set_text(self, text: str) -> None:
        self._renderable = text
        self.update(text)


class CoverDisplay(Static):
    def __init__(
        self,
        *,
        title: str,
        authors: list[str] | tuple[str, ...] | None = None,
        image_path: str | Path | None = None,
        terminal_graphics: bool = False,
        display_mode: str = "auto",
        media_type: str | None = None,
        source: str | None = None,
        cache_status: str | None = None,
        **kwargs: object,
    ) -> None:
        self.title = title
        self.authors = list(authors or [])
        self.image_path = Path(image_path) if image_path is not None else None
        self.terminal_graphics = terminal_graphics
        self.display_mode = display_mode
        self.media_type = media_type
        self.source = source
        self.cache_status = cache_status
        renderable = self._render_cover()
        super().__init__(renderable, **kwargs)
        self._renderable = renderable

    @property
    def renderable(self) -> str:
        return self._renderable

    def compose(self) -> ComposeResult:
        if self.display_mode == "off":
            return

        image_widget = self._image_widget()
        if image_widget is not None:
            yield image_widget
        yield Static(self._renderable, classes="cover-fallback")

    def _image_widget(self) -> Widget | None:
        if self.display_mode != "auto":
            return None
        if not self.terminal_graphics:
            return None
        if self.image_path is None or not self.image_path.exists():
            return None

        try:
            from textual_image.widget import Image

            return Image(str(self.image_path))
        except Exception:
            return None

    def _render_cover(self) -> str:
        if self.display_mode == "off":
            return ""

        author_text = ", ".join(self.authors) if self.authors else "Unknown author"
        lines = [self.title, author_text]
        if self.media_type:
            lines.append(f"Media type: {self.media_type}")
        if self.source:
            lines.append(f"Source: {self.source}")
        lines.append(self._cover_status_text())
        return "\n".join(lines)

    def _cover_status_text(self) -> str:
        if self.image_path is not None and (self.cache_status == "cached" or self.image_path.exists()):
            return "Cover cached"
        return "Cover unavailable"
