from pathlib import Path

from epub_tui import library
from epub_tui.library import LibraryRepository


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
