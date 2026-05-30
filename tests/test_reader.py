from pathlib import Path

from ebooklib import epub

from epub_tui.reader import EpubPreview, extract_epub_preview


def test_extract_epub_preview_reads_spine_text(tmp_path: Path) -> None:
    epub_path = tmp_path / "sample.epub"
    book = epub.EpubBook()
    book.set_identifier("sample")
    book.set_title("Sample EPUB")
    book.set_language("en")
    chapter = epub.EpubHtml(title="Chapter One", file_name="chapter.xhtml", lang="en")
    chapter.content = b"<html><body><h1>Chapter One</h1><p>Hello terminal reader.</p></body></html>"
    book.add_item(chapter)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)

    preview = extract_epub_preview(epub_path)

    assert isinstance(preview, EpubPreview)
    assert preview.title == "Sample EPUB"
    assert preview.sections[0].heading == "Chapter One"
    assert "Hello terminal reader." in preview.sections[0].text
