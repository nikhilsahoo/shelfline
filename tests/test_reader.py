from pathlib import Path

import pytest
from ebooklib import epub

from epub_tui.reader import (
    EpubOutlineItem,
    EpubPreview,
    EpubSection,
    ReaderError,
    extract_epub_preview,
)


def _chapter(title: str, file_name: str, content: bytes) -> epub.EpubHtml:
    chapter = epub.EpubHtml(title=title, file_name=file_name, lang="en")
    chapter.content = content
    return chapter


def _write_epub(
    epub_path: Path,
    chapters: list[epub.EpubHtml],
    *,
    title: str | None = "Sample EPUB",
    spine: list[object] | None = None,
) -> None:
    book = epub.EpubBook()
    book.set_identifier("sample")
    if title is not None:
        book.set_title(title)
    book.set_language("en")
    for chapter in chapters:
        book.add_item(chapter)
    book.spine = spine if spine is not None else ["nav", *chapters]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)


def _preview_with_sections(*headings: str) -> EpubPreview:
    sections = tuple(EpubSection(heading=heading, text=f"{heading} text") for heading in headings)
    outline = tuple(
        EpubOutlineItem(title=section.heading, section_index=index)
        for index, section in enumerate(sections)
    )
    return EpubPreview(title="Navigation Sample", outline=outline, sections=sections)


def test_extract_epub_preview_reads_spine_text_with_outline(tmp_path: Path) -> None:
    epub_path = tmp_path / "sample.epub"
    chapter = _chapter(
        "Chapter One",
        "chapter.xhtml",
        b"<html><body><h1>Chapter One</h1><p>Hello terminal reader.</p></body></html>",
    )
    _write_epub(epub_path, [chapter])

    preview = extract_epub_preview(epub_path)

    assert isinstance(preview, EpubPreview)
    assert preview.title == "Sample EPUB"
    assert preview.sections[0].heading == "Chapter One"
    assert "Hello terminal reader." in preview.sections[0].text
    assert preview.outline == (EpubOutlineItem(title="Chapter One", section_index=0),)


def test_epub_preview_section_count_returns_number_of_sections() -> None:
    preview = _preview_with_sections("One", "Two", "Three")

    assert preview.section_count == 3


def test_epub_preview_section_at_clamps_to_valid_range() -> None:
    preview = _preview_with_sections("One", "Two", "Three")

    assert preview.section_at(-5).heading == "One"
    assert preview.section_at(1).heading == "Two"
    assert preview.section_at(99).heading == "Three"


def test_epub_preview_next_section_index_clamps_at_last_section() -> None:
    preview = _preview_with_sections("One", "Two", "Three")

    assert preview.next_section_index(-5) == 1
    assert preview.next_section_index(0) == 1
    assert preview.next_section_index(1) == 2
    assert preview.next_section_index(2) == 2
    assert preview.next_section_index(99) == 2


def test_epub_preview_previous_section_index_clamps_at_zero() -> None:
    preview = _preview_with_sections("One", "Two", "Three")

    assert preview.previous_section_index(-5) == 0
    assert preview.previous_section_index(0) == 0
    assert preview.previous_section_index(1) == 0
    assert preview.previous_section_index(2) == 1
    assert preview.previous_section_index(99) == 1


def test_epub_preview_empty_sections_have_explicit_navigation_behavior() -> None:
    preview = _preview_with_sections()

    with pytest.raises(ReaderError, match="has no readable text sections"):
        preview.section_at(0)
    assert preview.next_section_index(0) == 0
    assert preview.previous_section_index(0) == 0


def test_title_falls_back_to_path_stem_when_metadata_is_missing(tmp_path: Path) -> None:
    epub_path = tmp_path / "untitled-book.epub"
    chapter = _chapter(
        "Chapter One",
        "chapter.xhtml",
        b"<html><body><h1>Chapter One</h1><p>Readable text.</p></body></html>",
    )
    _write_epub(epub_path, [chapter], title=None)

    preview = extract_epub_preview(epub_path)

    assert preview.title == "untitled-book"


def test_title_falls_back_to_path_stem_when_metadata_is_blank(tmp_path: Path) -> None:
    epub_path = tmp_path / "blank-title.epub"
    chapter = _chapter(
        "Chapter One",
        "chapter.xhtml",
        b"<html><body><h1>Chapter One</h1><p>Readable text.</p></body></html>",
    )
    _write_epub(epub_path, [chapter], title="   ")

    preview = extract_epub_preview(epub_path)

    assert preview.title == "blank-title"


def test_headings_prefer_h1_then_h2_then_h3_then_item_name(tmp_path: Path) -> None:
    epub_path = tmp_path / "headings.epub"
    h1 = _chapter(
        "Item H1",
        "h1.xhtml",
        b"<html><body><h2>Wrong H2</h2><h1>Right H1</h1><p>One.</p></body></html>",
    )
    h2 = _chapter(
        "Item H2",
        "h2.xhtml",
        b"<html><body><h2>Right H2</h2><h3>Wrong H3</h3><p>Two.</p></body></html>",
    )
    h3 = _chapter(
        "Item H3",
        "h3.xhtml",
        b"<html><body><h3>Right H3</h3><p>Three.</p></body></html>",
    )
    fallback = _chapter(
        "Item Fallback",
        "fallback.xhtml",
        b"<html><body><p>Four.</p></body></html>",
    )
    _write_epub(epub_path, [h1, h2, h3, fallback])

    preview = extract_epub_preview(epub_path)

    assert [section.heading for section in preview.sections] == [
        "Right H1",
        "Right H2",
        "Right H3",
        "fallback.xhtml",
    ]


def test_empty_sections_are_skipped(tmp_path: Path) -> None:
    epub_path = tmp_path / "empty-first.epub"
    empty = _chapter("Empty", "empty.xhtml", b"<html><body><h1>Empty</h1></body></html>")
    readable = _chapter(
        "Readable",
        "readable.xhtml",
        b"<html><body><h1>Readable</h1><p>Keep this section.</p></body></html>",
    )
    _write_epub(epub_path, [empty, readable])

    preview = extract_epub_preview(epub_path)

    assert [section.heading for section in preview.sections] == ["Readable"]
    assert preview.outline == (EpubOutlineItem(title="Readable", section_index=0),)


def test_reader_error_when_no_readable_text_sections_are_found(tmp_path: Path) -> None:
    epub_path = tmp_path / "empty.epub"
    chapter = _chapter("Empty", "empty.xhtml", b"<html><body><h1>Empty</h1></body></html>")
    _write_epub(epub_path, [chapter])

    with pytest.raises(ReaderError, match="No readable text sections"):
        extract_epub_preview(epub_path)


def test_malformed_epub_is_wrapped_in_reader_error(tmp_path: Path) -> None:
    epub_path = tmp_path / "not-an-epub.epub"
    epub_path.write_bytes(b"not an epub archive")

    with pytest.raises(ReaderError, match="Could not read EPUB preview"):
        extract_epub_preview(epub_path)


def test_reader_error_when_only_non_spine_documents_have_text(tmp_path: Path) -> None:
    epub_path = tmp_path / "non-spine.epub"
    chapter = _chapter(
        "Non Spine",
        "chapter.xhtml",
        b"<html><body><h1>Non Spine</h1><p>Do not preview this.</p></body></html>",
    )
    _write_epub(epub_path, [chapter], spine=["nav"])

    with pytest.raises(ReaderError, match="No readable text sections"):
        extract_epub_preview(epub_path)
