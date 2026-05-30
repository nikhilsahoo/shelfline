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

    def mark_read(self, local_file_path: Path, is_read: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE books SET is_read = ? WHERE local_file_path = ?",
                (int(is_read), self._path_to_text(local_file_path)),
            )

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
