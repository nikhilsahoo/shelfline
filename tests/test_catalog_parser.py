from pathlib import Path

import pytest

from epub_tui.catalog.parser import OpdsParseError, parse_opds_feed


def test_parse_navigation_feed_resolves_relative_links(fixture_dir: Path) -> None:
    xml = (fixture_dir / "opds" / "navigation.xml").read_text(encoding="utf-8")

    feed = parse_opds_feed(xml, source_url="https://example.test/root.xml")

    assert feed.title == "Example Catalog"
    assert feed.entries[0].title == "Fiction"
    assert feed.entries[0].navigation_url == "https://example.test/opds/fiction.xml"
    assert feed.entries[0].acquisition_links == []


def test_parse_acquisition_feed_extracts_epub_and_pdf(fixture_dir: Path) -> None:
    xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")

    feed = parse_opds_feed(xml, source_url="https://example.test/opds/fiction.xml")

    entry = feed.entries[0]
    assert entry.title == "Sample Book"
    assert entry.authors == ["Ada Writer"]
    assert entry.summary == "A short fixture book."
    assert entry.cover_image_url == "https://example.test/opds/covers/sample.jpg"
    assert entry.thumbnail_url == "https://example.test/opds/covers/sample-thumb.jpg"
    assert entry.best_epub_link().href == "https://example.test/opds/books/sample.epub"
    assert {link.media_type for link in entry.acquisition_links} == {
        "application/epub+zip",
        "application/pdf",
    }


def test_invalid_feed_raises_parse_error(fixture_dir: Path) -> None:
    xml = (fixture_dir / "opds" / "invalid.xml").read_text(encoding="utf-8")

    with pytest.raises(OpdsParseError, match="Invalid OPDS feed"):
        parse_opds_feed(xml, source_url="https://example.test/broken.xml")
