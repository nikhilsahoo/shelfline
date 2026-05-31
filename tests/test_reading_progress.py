from pathlib import Path

from epub_tui import library
from epub_tui.library import BookRecord, LibraryRepository


def test_reading_progress_round_trip_preserves_section_and_position(
    tmp_path: Path,
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"

    repo.save_reading_progress(
        library.ReadingProgress(
            local_file_path=book_path,
            section_index=3,
            position=125,
        )
    )

    progress = repo.get_reading_progress(book_path)

    assert progress is not None
    assert progress.local_file_path == book_path
    assert progress.section_index == 3
    assert progress.position == 125
    assert progress.updated_at is not None


def test_reading_progress_updates_existing_path(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"

    repo.save_reading_progress(
        library.ReadingProgress(book_path, section_index=1, position=10)
    )
    repo.save_reading_progress(
        library.ReadingProgress(book_path, section_index=5, position=250)
    )

    progress = repo.get_reading_progress(book_path)

    assert progress is not None
    assert progress.section_index == 5
    assert progress.position == 250


def test_reading_progress_returns_none_for_missing_path(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()

    assert repo.get_reading_progress(tmp_path / "books" / "missing.epub") is None


def test_delete_book_clears_reading_progress_for_deleted_path_only(
    tmp_path: Path,
) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"
    other_path = tmp_path / "books" / "other.epub"
    book_path.parent.mkdir()
    book_path.write_bytes(b"book")
    other_path.write_bytes(b"other")
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
    repo.save_reading_progress(
        library.ReadingProgress(book_path, section_index=2, position=40)
    )
    repo.save_reading_progress(
        library.ReadingProgress(other_path, section_index=4, position=80)
    )

    repo.delete_book(book_path, remove_file=False)

    assert repo.get_reading_progress(book_path) is None
    other_progress = repo.get_reading_progress(other_path)
    assert other_progress is not None
    assert other_progress.section_index == 4
    assert other_progress.position == 80


def test_bookmarks_round_trip_order_and_delete(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"

    third = repo.add_bookmark(
        library.Bookmark(book_path, section_index=3, position=25, label="Third")
    )
    first = repo.add_bookmark(
        library.Bookmark(book_path, section_index=1, position=20, label="First")
    )
    second = repo.add_bookmark(
        library.Bookmark(book_path, section_index=1, position=10, label="Second")
    )

    assert first.id is not None
    assert first.created_at is not None
    assert [bookmark.label for bookmark in repo.list_bookmarks(book_path)] == [
        "Second",
        "First",
        "Third",
    ]

    repo.delete_bookmark(second.id)

    remaining = repo.list_bookmarks(book_path)
    assert [bookmark.id for bookmark in remaining] == [first.id, third.id]
    assert remaining[0].local_file_path == book_path
    assert remaining[0].section_index == 1
    assert remaining[0].position == 20


def test_find_bookmark_returns_matching_section_and_position_only(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"
    other_path = tmp_path / "books" / "other.epub"

    expected = repo.add_bookmark(
        library.Bookmark(book_path, section_index=1, position=10, label="Expected")
    )
    repo.add_bookmark(
        library.Bookmark(book_path, section_index=1, position=20, label="Wrong position")
    )
    repo.add_bookmark(
        library.Bookmark(book_path, section_index=2, position=10, label="Wrong section")
    )
    repo.add_bookmark(
        library.Bookmark(other_path, section_index=1, position=10, label="Wrong book")
    )

    bookmark = repo.find_bookmark(book_path, section_index=1, position=10)

    assert bookmark == expected
    assert repo.find_bookmark(book_path, section_index=9, position=99) is None


def test_delete_bookmarks_at_position_removes_all_matching_rows(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"
    other_path = tmp_path / "books" / "other.epub"

    repo.add_bookmark(
        library.Bookmark(book_path, section_index=1, position=10, label="Duplicate A")
    )
    repo.add_bookmark(
        library.Bookmark(book_path, section_index=1, position=10, label="Duplicate B")
    )
    wrong_position = repo.add_bookmark(
        library.Bookmark(book_path, section_index=1, position=20, label="Wrong position")
    )
    wrong_section = repo.add_bookmark(
        library.Bookmark(book_path, section_index=2, position=10, label="Wrong section")
    )
    wrong_book = repo.add_bookmark(
        library.Bookmark(other_path, section_index=1, position=10, label="Wrong book")
    )

    deleted_count = repo.delete_bookmarks_at_position(
        book_path, section_index=1, position=10
    )

    assert deleted_count == 2
    assert [bookmark.id for bookmark in repo.list_bookmarks(book_path)] == [
        wrong_position.id,
        wrong_section.id,
    ]
    assert [bookmark.id for bookmark in repo.list_bookmarks(other_path)] == [
        wrong_book.id
    ]


def test_delete_book_clears_bookmarks_for_deleted_path_only(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    book_path = tmp_path / "books" / "sample.epub"
    other_path = tmp_path / "books" / "other.epub"
    book_path.parent.mkdir()
    book_path.write_bytes(b"book")
    other_path.write_bytes(b"other")
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
    repo.add_bookmark(library.Bookmark(book_path, section_index=2, label="Sample"))
    other = repo.add_bookmark(
        library.Bookmark(other_path, section_index=4, label="Other")
    )

    repo.delete_book(book_path, remove_file=False)

    assert repo.list_bookmarks(book_path) == []
    assert [bookmark.id for bookmark in repo.list_bookmarks(other_path)] == [other.id]
