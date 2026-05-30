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


def test_parse_navigation_feed_accepts_opds_subsection_uri_relation() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Catalog</title>
  <entry>
    <title>Classics</title>
    <link rel="http://opds-spec.org/subsection" href="classics.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation"/>
  </entry>
</feed>
"""

    feed = parse_opds_feed(xml, source_url="https://example.test/opds/fiction.xml")

    assert feed.entries[0].navigation_url == "https://example.test/opds/classics.xml"


def test_parse_navigation_feed_accepts_atom_catalog_links_without_rel() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Catalog</title>
  <entry>
    <title>Series</title>
    <link href="series.xml" type="application/atom+xml;profile=opds-catalog;kind=navigation"/>
  </entry>
</feed>
"""

    feed = parse_opds_feed(xml, source_url="https://example.test/opds/root.xml")

    assert feed.entries[0].navigation_url == "https://example.test/opds/series.xml"


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


def test_parse_feed_sanitizes_links_resolved_from_credentialed_source_url() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Private</title>
  <entry>
    <title>Private Book</title>
    <link rel="subsection" href="sections/fiction.xml"/>
    <link rel="http://opds-spec.org/image" href="covers/private.jpg"/>
    <link rel="http://opds-spec.org/acquisition" href="books/private.epub" type="application/epub+zip"/>
  </entry>
</feed>
"""

    feed = parse_opds_feed(xml, source_url="https://alice:secret@example.test/opds/root.xml")

    entry = feed.entries[0]
    assert feed.source_url == "https://example.test/opds/root.xml"
    assert entry.navigation_url == "https://example.test/opds/sections/fiction.xml"
    assert entry.cover_image_url == "https://example.test/opds/covers/private.jpg"
    assert entry.best_epub_link().href == "https://example.test/opds/books/private.epub"
    assert "alice" not in entry.navigation_url
    assert "secret" not in entry.cover_image_url
    assert "alice" not in entry.best_epub_link().href
    assert "secret" not in entry.best_epub_link().href


def test_parse_feed_sanitizes_absolute_credentialed_link_hrefs() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Private</title>
  <entry>
    <title>Private Book</title>
    <link rel="http://opds-spec.org/image" href="https://alice:secret@example.test/covers/private.jpg"/>
    <link rel="http://opds-spec.org/acquisition" href="https://alice:secret@example.test/books/private.epub" type="application/epub+zip"/>
  </entry>
</feed>
"""

    feed = parse_opds_feed(xml, source_url="https://example.test/opds/root.xml")

    entry = feed.entries[0]
    assert entry.cover_image_url == "https://example.test/covers/private.jpg"
    assert entry.best_epub_link().href == "https://example.test/books/private.epub"
    assert "alice" not in entry.cover_image_url
    assert "secret" not in entry.cover_image_url
    assert "alice" not in entry.best_epub_link().href
    assert "secret" not in entry.best_epub_link().href


def test_parse_acquisition_feed_accepts_open_access_subrelation() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Open Access</title>
  <id>urn:example:open-access</id>
  <updated>2026-05-30T00:00:00Z</updated>
  <entry>
    <title>Open Book</title>
    <id>urn:isbn:9780000000002</id>
    <updated>2026-05-30T00:00:00Z</updated>
    <link rel="http://opds-spec.org/acquisition/open-access" href="books/open.epub" type="application/epub+zip" title="Open EPUB"/>
    <link rel="http://opds-spec.org/acquisition-not-real" href="books/not-real.epub" type="application/epub+zip" title="Not Real"/>
  </entry>
</feed>
"""

    feed = parse_opds_feed(xml, source_url="https://example.test/opds/open.xml")

    entry = feed.entries[0]
    assert [link.relation for link in entry.acquisition_links] == [
        "http://opds-spec.org/acquisition/open-access"
    ]
    assert entry.best_epub_link().href == "https://example.test/opds/books/open.epub"


def test_parse_feed_preserves_missing_optional_values_as_none() -> None:
    xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Minimal Catalog</title>
  <entry>
    <title>Untimed Book</title>
  </entry>
</feed>
"""

    feed = parse_opds_feed(xml, "https://example.test/minimal.xml")

    assert feed.updated is None
    assert feed.entries[0].identifier is None
    assert feed.entries[0].updated is None


def test_invalid_feed_raises_parse_error(fixture_dir: Path) -> None:
    xml = (fixture_dir / "opds" / "invalid.xml").read_text(encoding="utf-8")

    with pytest.raises(OpdsParseError, match="Invalid OPDS feed"):
        parse_opds_feed(xml, source_url="https://example.test/broken.xml")
