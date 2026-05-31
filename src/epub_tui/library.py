from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator


@dataclass(frozen=True)
class BookRecord:
    title: str
    authors: list[str]
    identifiers: list[str]
    source_catalog: str
    source_entry_url: str | None
    acquisition_url: str
    media_type: str
    cover_image_url: str | None
    cover_image_path: Path | None
    local_file_path: Path
    is_read: bool = False
    deleted_at: str | None = None


@dataclass(frozen=True)
class ReadingProgress:
    local_file_path: Path
    section_index: int
    position: int = 0
    updated_at: str | None = None


@dataclass(frozen=True)
class LibrarySearch:
    query: str | None = None
    source_catalog: str | None = None
    media_type: str | None = None
    is_read: bool | None = None
    include_deleted: bool = False


class LibraryRepository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    authors_json TEXT NOT NULL,
                    identifiers_json TEXT NOT NULL,
                    source_catalog TEXT NOT NULL,
                    source_entry_url TEXT,
                    acquisition_url TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    cover_image_url TEXT,
                    cover_image_path TEXT,
                    local_file_path TEXT NOT NULL UNIQUE,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    deleted_at TEXT,
                    downloaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_cache (
                    url TEXT PRIMARY KEY,
                    source_catalog TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS reading_progress (
                    local_file_path TEXT PRIMARY KEY,
                    section_index INTEGER NOT NULL,
                    position INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def add_book(self, book: BookRecord) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO books (
                    title,
                    authors_json,
                    identifiers_json,
                    source_catalog,
                    source_entry_url,
                    acquisition_url,
                    media_type,
                    cover_image_url,
                    cover_image_path,
                    local_file_path,
                    is_read,
                    deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(local_file_path) DO UPDATE SET
                    title = excluded.title,
                    authors_json = excluded.authors_json,
                    identifiers_json = excluded.identifiers_json,
                    source_catalog = excluded.source_catalog,
                    source_entry_url = excluded.source_entry_url,
                    acquisition_url = excluded.acquisition_url,
                    media_type = excluded.media_type,
                    cover_image_url = excluded.cover_image_url,
                    cover_image_path = excluded.cover_image_path,
                    is_read = excluded.is_read,
                    deleted_at = excluded.deleted_at
                """,
                (
                    book.title,
                    json.dumps(book.authors),
                    json.dumps(book.identifiers),
                    book.source_catalog,
                    book.source_entry_url,
                    book.acquisition_url,
                    book.media_type,
                    book.cover_image_url,
                    self._path_to_text(book.cover_image_path),
                    self._path_to_text(book.local_file_path),
                    int(book.is_read),
                    book.deleted_at,
                ),
            )

    def list_books(self, include_deleted: bool = False) -> list[BookRecord]:
        where_clause = "" if include_deleted else "WHERE deleted_at IS NULL"
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    title,
                    authors_json,
                    identifiers_json,
                    source_catalog,
                    source_entry_url,
                    acquisition_url,
                    media_type,
                    cover_image_url,
                    cover_image_path,
                    local_file_path,
                    is_read,
                    deleted_at
                FROM books
                {where_clause}
                ORDER BY downloaded_at, id
                """
            ).fetchall()
        return [self._book_from_row(row) for row in rows]

    def search_books(self, search: LibrarySearch) -> list[BookRecord]:
        clauses: list[str] = []
        params: list[object] = []
        if not search.include_deleted:
            clauses.append("deleted_at IS NULL")
        if search.source_catalog:
            clauses.append("source_catalog = ?")
            params.append(search.source_catalog)
        if search.media_type:
            clauses.append("media_type = ?")
            params.append(search.media_type)
        if search.is_read is not None:
            clauses.append("is_read = ?")
            params.append(int(search.is_read))

        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    title,
                    authors_json,
                    identifiers_json,
                    source_catalog,
                    source_entry_url,
                    acquisition_url,
                    media_type,
                    cover_image_url,
                    cover_image_path,
                    local_file_path,
                    is_read,
                    deleted_at
                FROM books
                {where_clause}
                ORDER BY downloaded_at, id
                """,
                tuple(params),
            ).fetchall()
        books = [self._book_from_row(row) for row in rows]
        if search.query:
            return [
                book
                for book in books
                if self._book_matches_literal_query(book, search.query)
            ]
        return books

    def mark_read(self, local_file_path: Path, is_read: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE books SET is_read = ? WHERE local_file_path = ?",
                (int(is_read), self._path_to_text(local_file_path)),
            )

    def save_reading_progress(self, progress: ReadingProgress) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO reading_progress (
                    local_file_path,
                    section_index,
                    position
                )
                VALUES (?, ?, ?)
                ON CONFLICT(local_file_path) DO UPDATE SET
                    section_index = excluded.section_index,
                    position = excluded.position,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    self._path_to_text(progress.local_file_path),
                    progress.section_index,
                    progress.position,
                ),
            )

    def get_reading_progress(self, local_file_path: Path) -> ReadingProgress | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT local_file_path, section_index, position, updated_at
                FROM reading_progress
                WHERE local_file_path = ?
                """,
                (self._path_to_text(local_file_path),),
            ).fetchone()
        return self._reading_progress_from_row(row) if row is not None else None

    def delete_book(self, local_file_path: Path, remove_file: bool = True) -> None:
        path_text = self._path_to_text(Path(local_file_path))
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT local_file_path
                FROM books
                WHERE local_file_path = ? AND deleted_at IS NULL
                """,
                (path_text,),
            ).fetchone()
            if row is None:
                return

            cursor = connection.execute(
                """
                UPDATE books
                SET deleted_at = CURRENT_TIMESTAMP
                WHERE local_file_path = ? AND deleted_at IS NULL
                """,
                (path_text,),
            )
            if cursor.rowcount == 0:
                return

            connection.execute(
                "DELETE FROM reading_progress WHERE local_file_path = ?",
                (path_text,),
            )

            deleted_path = Path(row["local_file_path"])
            if remove_file and deleted_path.exists():
                deleted_path.unlink()

    def save_feed_cache(
        self, source_catalog: str, url: str, title: str, body: str
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO feed_cache (url, source_catalog, title, body)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    source_catalog = excluded.source_catalog,
                    title = excluded.title,
                    body = excluded.body,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                (url, source_catalog, title, body),
            )

    def get_feed_cache(self, url: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT url, source_catalog, title, body, fetched_at
                FROM feed_cache
                WHERE url = ?
                """,
                (url,),
            ).fetchone()
        return dict(row) if row is not None else None

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _path_to_text(path: Path | None) -> str | None:
        return str(path) if path is not None else None

    @staticmethod
    def _book_matches_literal_query(book: BookRecord, query: str) -> bool:
        folded_query = query.casefold()
        return folded_query in book.title.casefold() or any(
            folded_query in author.casefold() for author in book.authors
        )

    @staticmethod
    def _book_from_row(row: sqlite3.Row) -> BookRecord:
        cover_image_path = row["cover_image_path"]
        return BookRecord(
            title=row["title"],
            authors=json.loads(row["authors_json"]),
            identifiers=json.loads(row["identifiers_json"]),
            source_catalog=row["source_catalog"],
            source_entry_url=row["source_entry_url"],
            acquisition_url=row["acquisition_url"],
            media_type=row["media_type"],
            cover_image_url=row["cover_image_url"],
            cover_image_path=Path(cover_image_path) if cover_image_path else None,
            local_file_path=Path(row["local_file_path"]),
            is_read=bool(row["is_read"]),
            deleted_at=row["deleted_at"],
        )

    @staticmethod
    def _reading_progress_from_row(row: sqlite3.Row) -> ReadingProgress:
        return ReadingProgress(
            local_file_path=Path(row["local_file_path"]),
            section_index=row["section_index"],
            position=row["position"],
            updated_at=row["updated_at"],
        )
