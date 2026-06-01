from __future__ import annotations

from pathlib import Path

from shelfline.library import BookRecord, LibraryRepository, LibrarySearch


def _book(
    tmp_path: Path,
    title: str,
    *,
    authors: list[str],
    catalog: str = "Example",
    media_type: str = "application/epub+zip",
    is_read: bool = False,
) -> BookRecord:
    path = tmp_path / f"{title}.epub"
    path.write_bytes(b"book")
    return BookRecord(
        title=title,
        authors=authors,
        identifiers=[f"urn:{title}"],
        source_catalog=catalog,
        source_entry_url=None,
        acquisition_url=f"https://example.test/{title}",
        media_type=media_type,
        cover_image_url=None,
        cover_image_path=None,
        local_file_path=path,
        is_read=is_read,
    )


def test_search_books_filters_by_title_and_author(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, "Dune", authors=["Frank Herbert"]))
    repo.add_book(_book(tmp_path, "Foundation", authors=["Isaac Asimov"]))

    assert [book.title for book in repo.search_books(LibrarySearch(query="dune"))] == ["Dune"]
    assert [book.title for book in repo.search_books(LibrarySearch(query="asimov"))] == [
        "Foundation"
    ]


def test_search_books_treats_like_metacharacters_as_literal_text(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, "100% True", authors=["Literal Percent"]))
    repo.add_book(_book(tmp_path, "Under_score", authors=["Literal Underscore"]))
    repo.add_book(_book(tmp_path, "Escaped Author", authors=["Back\\Slash"]))
    repo.add_book(_book(tmp_path, "Plain Book", authors=["Ordinary Author"]))

    assert [book.title for book in repo.search_books(LibrarySearch(query="%"))] == [
        "100% True"
    ]
    assert [book.title for book in repo.search_books(LibrarySearch(query="_"))] == [
        "Under_score"
    ]
    assert [book.title for book in repo.search_books(LibrarySearch(query="\\"))] == [
        "Escaped Author"
    ]


def test_search_books_matches_unicode_title_case_insensitively(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, "Éclair", authors=["Patisserie Guide"]))
    repo.add_book(_book(tmp_path, "Plain Book", authors=["Ordinary Author"]))

    assert [book.title for book in repo.search_books(LibrarySearch(query="éclair"))] == [
        "Éclair"
    ]


def test_search_books_matches_unicode_author_case_insensitively(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, "Memoir", authors=["René"]))
    repo.add_book(_book(tmp_path, "Plain Book", authors=["Ordinary Author"]))

    assert [book.title for book in repo.search_books(LibrarySearch(query="rené"))] == [
        "Memoir"
    ]


def test_search_books_filters_by_catalog_format_and_read_state(tmp_path: Path) -> None:
    repo = LibraryRepository(tmp_path / "state.db")
    repo.initialize()
    repo.add_book(_book(tmp_path, "Read EPUB", authors=["A"], catalog="One", is_read=True))
    repo.add_book(
        _book(
            tmp_path,
            "Unread PDF",
            authors=["B"],
            catalog="Two",
            media_type="application/pdf",
            is_read=False,
        )
    )

    assert [book.title for book in repo.search_books(LibrarySearch(source_catalog="One"))] == [
        "Read EPUB"
    ]
    assert [book.title for book in repo.search_books(LibrarySearch(media_type="application/pdf"))] == [
        "Unread PDF"
    ]
    assert [book.title for book in repo.search_books(LibrarySearch(is_read=True))] == [
        "Read EPUB"
    ]
    assert [book.title for book in repo.search_books(LibrarySearch(is_read=False))] == [
        "Unread PDF"
    ]
