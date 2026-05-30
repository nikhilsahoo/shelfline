from pathlib import Path
import sqlite3

from epub_tui.library import BookRecord, LibraryRepository


def test_repository_initializes_schema_and_saves_book(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()

    book = BookRecord(
        title="Sample Book",
        authors=["Ada Writer"],
        identifiers=["urn:isbn:9780000000001"],
        source_catalog="Private",
        source_entry_url="https://example.test/opds/book",
        acquisition_url="https://example.test/books/sample.epub",
        media_type="application/epub+zip",
        cover_image_url="https://example.test/covers/sample.jpg",
        cover_image_path=tmp_path / "covers" / "sample.jpg",
        local_file_path=tmp_path / "books" / "sample.epub",
        is_read=False,
    )

    repo.add_book(book)

    books = repo.list_books()
    assert len(books) == 1
    assert books[0].title == "Sample Book"
    assert books[0].authors == ["Ada Writer"]
    assert books[0].cover_image_url == "https://example.test/covers/sample.jpg"
    assert books[0].cover_image_path == tmp_path / "covers" / "sample.jpg"
    assert books[0].is_read is False


def test_repository_marks_book_read_and_unread(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"
    book_path.parent.mkdir()
    book_path.write_bytes(b"book")
    repo.add_book(
        BookRecord(
            title="Sample Book",
            authors=[],
            identifiers=[],
            source_catalog="Private",
            source_entry_url=None,
            acquisition_url="https://example.test/books/sample.epub",
            media_type="application/epub+zip",
            cover_image_url=None,
            cover_image_path=None,
            local_file_path=book_path,
            is_read=False,
        )
    )

    repo.mark_read(book_path, is_read=True)
    assert repo.list_books()[0].is_read is True

    repo.mark_read(book_path, is_read=False)
    assert repo.list_books()[0].is_read is False


def test_repository_deletes_local_book_and_hides_it_by_default(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"
    book_path.parent.mkdir()
    book_path.write_bytes(b"book")
    repo.add_book(
        BookRecord(
            title="Sample Book",
            authors=[],
            identifiers=[],
            source_catalog="Private",
            source_entry_url=None,
            acquisition_url="https://example.test/books/sample.epub",
            media_type="application/epub+zip",
            cover_image_url=None,
            cover_image_path=None,
            local_file_path=book_path,
            is_read=False,
        )
    )

    repo.delete_book(book_path, remove_file=True)

    assert not book_path.exists()
    assert repo.list_books() == []
    assert repo.list_books(include_deleted=True)[0].deleted_at is not None


def test_repository_does_not_delete_untracked_local_file(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    untracked_path = tmp_path / "books" / "untracked.epub"
    untracked_path.parent.mkdir()
    untracked_path.write_bytes(b"untracked")

    repo.delete_book(untracked_path, remove_file=True)

    assert untracked_path.exists()
    assert untracked_path.read_bytes() == b"untracked"
    assert repo.list_books(include_deleted=True) == []


def test_repository_does_not_remove_file_when_metadata_delete_fails(
    tmp_path: Path,
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"
    book_path.parent.mkdir()
    book_path.write_bytes(b"book")
    repo.add_book(
        BookRecord(
            title="Sample Book",
            authors=[],
            identifiers=[],
            source_catalog="Private",
            source_entry_url=None,
            acquisition_url="https://example.test/books/sample.epub",
            media_type="application/epub+zip",
            cover_image_url=None,
            cover_image_path=None,
            local_file_path=book_path,
            is_read=False,
        )
    )

    def fail_metadata_delete(local_file_path: Path) -> Path | None:
        raise sqlite3.OperationalError("database is locked")

    repo._mark_book_deleted = fail_metadata_delete  # type: ignore[method-assign]

    try:
        repo.delete_book(book_path, remove_file=True)
    except sqlite3.OperationalError as error:
        assert str(error) == "database is locked"
    else:
        raise AssertionError("Expected metadata delete failure")

    assert book_path.exists()
    assert repo.list_books()[0].deleted_at is None


def test_feed_cache_round_trip(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()

    repo.save_feed_cache("Private", "https://example.test/opds", "Catalog", "<feed />")

    cached = repo.get_feed_cache("https://example.test/opds")
    assert cached is not None
    assert cached["title"] == "Catalog"
    assert cached["body"] == "<feed />"
