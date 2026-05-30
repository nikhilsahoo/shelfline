from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

import httpx

from epub_tui.catalog.client import CatalogClient
from epub_tui.catalog.models import CatalogEntry, CatalogFeed
from epub_tui.catalog.parser import parse_opds_feed
from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.downloads import DownloadError, DownloadProgress, DownloadService
from epub_tui.library import BookRecord, LibraryRepository


StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[DownloadProgress], None]
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


class CatalogWorkflow:
    def __init__(
        self,
        config: AppConfig,
        state_db: Path,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._http_client = http_client or httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
        )
        self._catalog_client = CatalogClient(self._http_client)
        self._download_service = DownloadService(self._http_client)
        self.library = LibraryRepository(state_db)
        self.library.initialize()

    async def fetch_catalog(
        self,
        catalog: CatalogConfig,
        url: str | None = None,
        on_status: StatusCallback | None = None,
    ) -> CatalogFeed:
        target_url = url or catalog.url
        _emit(on_status, "Fetching catalog...")
        body = await self._catalog_client.fetch_feed(
            _catalog_for_url(catalog, target_url),
            target_url,
        )
        feed = parse_opds_feed(body, source_url=_opds_parse_base_url(target_url))
        feed = replace(feed, source_url=target_url)
        self.library.save_feed_cache(catalog.name, target_url, feed.title, body)
        _emit(on_status, "Catalog loaded")
        return feed

    async def download_best_epub(
        self,
        catalog: CatalogConfig,
        entry: CatalogEntry,
        on_status: StatusCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> Path:
        link = entry.best_epub_link()
        if link is None:
            raise DownloadError("No EPUB acquisition link exists")

        _emit(on_status, "Starting download...")
        downloaded_path = await self._download_service.download(
            url=link.href,
            destination_dir=self.config.library_path,
            filename=_safe_epub_filename(entry.title),
            auth=_auth_tuple(catalog) if _same_origin(catalog.url, link.href) else None,
            on_progress=on_progress,
        )
        self.library.add_book(
            BookRecord(
                title=entry.title,
                authors=entry.authors,
                identifiers=[entry.identifier] if entry.identifier else [],
                source_catalog=catalog.name,
                source_entry_url=None,
                acquisition_url=link.href,
                media_type=link.media_type,
                cover_image_url=entry.cover_image_url or entry.thumbnail_url,
                cover_image_path=None,
                local_file_path=downloaded_path,
                is_read=False,
            )
        )
        _emit(on_status, "Download complete")
        return downloaded_path

    async def aclose(self) -> None:
        await self._http_client.aclose()


def _emit(callback: StatusCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _auth_tuple(catalog: CatalogConfig) -> tuple[str, str] | None:
    if catalog.auth is None:
        return None
    return catalog.auth["username"], catalog.auth["password"]


def _catalog_for_url(catalog: CatalogConfig, url: str) -> CatalogConfig:
    if catalog.auth is None or _same_origin(catalog.url, url):
        return catalog
    return replace(catalog, auth=None)


def _same_origin(left_url: str, right_url: str) -> bool:
    left = urlsplit(left_url)
    right = urlsplit(right_url)
    return (
        left.scheme == right.scheme
        and left.hostname == right.hostname
        and _origin_port(left) == _origin_port(right)
    )


def _origin_port(parts) -> int | None:
    if parts.port is not None:
        return parts.port
    if parts.scheme == "http":
        return 80
    if parts.scheme == "https":
        return 443
    return None


def _safe_epub_filename(title: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    if not stem or stem.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        stem = "book"
    return f"{stem}.epub"


def _opds_parse_base_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.path.endswith("/") or Path(parts.path).suffix:
        return url
    return urlunsplit((parts.scheme, parts.netloc, f"{parts.path}/", parts.query, parts.fragment))
