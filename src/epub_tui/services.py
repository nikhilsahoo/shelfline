from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

import httpx

from epub_tui.catalog.client import CatalogClient
from epub_tui.catalog.models import AcquisitionLink, CatalogEntry, CatalogFeed
from epub_tui.catalog.parser import parse_opds_feed, sanitize_text_url_credentials, sanitize_url_credentials
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
_MEDIA_TYPE_EXTENSIONS = {
    "application/epub+zip": ".epub",
    "application/pdf": ".pdf",
    "image/vnd.djvu": ".djvu",
    "image/x-djvu": ".djvu",
    "application/x-djvu": ".djvu",
    "application/vnd.comicbook+zip": ".cbz",
    "application/x-cbz": ".cbz",
    "application/vnd.comicbook-rar": ".cbr",
    "application/x-cbr": ".cbr",
}
_KNOWN_ACQUISITION_EXTENSIONS = {".epub", ".pdf", ".djvu", ".djv", ".cbz", ".cbr"}


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
        target_url = sanitize_url_credentials(url or catalog.url)
        _emit(on_status, "Fetching catalog...")
        body = await self._catalog_client.fetch_feed(
            _catalog_for_url(catalog, target_url),
            target_url,
        )
        feed = parse_opds_feed(body, source_url=_opds_parse_base_url(target_url))
        feed = replace(feed, source_url=target_url)
        self.library.save_feed_cache(
            catalog.name,
            target_url,
            feed.title,
            sanitize_text_url_credentials(body),
        )
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

        return await self.download_acquisition(
            catalog,
            entry,
            link=link,
            on_status=on_status,
            on_progress=on_progress,
        )

    async def download_acquisition(
        self,
        catalog: CatalogConfig,
        entry: CatalogEntry,
        link: AcquisitionLink | None = None,
        on_status: StatusCallback | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> Path:
        selected_link = link or _best_acquisition_link(entry)
        if selected_link is None:
            raise DownloadError("No acquisition link exists")

        href = sanitize_url_credentials(selected_link.href)
        _emit(on_status, "Starting download...")
        downloaded_path = await self._download_service.download(
            url=href,
            destination_dir=self.config.library_path,
            filename=_safe_acquisition_filename(entry.title, selected_link),
            auth=_auth_tuple(catalog) if _same_origin(catalog.url, href) else None,
            on_progress=on_progress,
        )
        self.library.add_book(
            BookRecord(
                title=entry.title,
                authors=entry.authors,
                identifiers=[entry.identifier] if entry.identifier else [],
                source_catalog=catalog.name,
                source_entry_url=None,
                acquisition_url=href,
                media_type=selected_link.media_type,
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
        return replace(catalog, url=sanitize_url_credentials(catalog.url))
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
    return _safe_filename(title, ".epub")


def _best_acquisition_link(entry: CatalogEntry) -> AcquisitionLink | None:
    epub_link = entry.best_epub_link()
    if epub_link is not None:
        return epub_link
    return entry.acquisition_links[0] if entry.acquisition_links else None


def _safe_acquisition_filename(title: str, link: AcquisitionLink) -> str:
    return _safe_filename(title, _extension_for_link(link))


def _safe_filename(title: str, extension: str) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', " ", title)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    if not stem or stem.split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        stem = "book"
    if Path(stem).suffix.lower() == extension:
        return stem
    return f"{stem}{extension}"


def _extension_for_link(link: AcquisitionLink) -> str:
    media_extension = _MEDIA_TYPE_EXTENSIONS.get(link.media_type.lower())
    if media_extension is not None:
        return media_extension

    for value in (link.title, urlsplit(link.href).path):
        if not value:
            continue
        extension = Path(value).suffix.lower()
        if extension in _KNOWN_ACQUISITION_EXTENSIONS:
            return extension
    return ".bin"


def _opds_parse_base_url(url: str) -> str:
    url = sanitize_url_credentials(url)
    parts = urlsplit(url)
    if parts.path.endswith("/") or Path(parts.path).suffix:
        return url
    return urlunsplit((parts.scheme, parts.netloc, f"{parts.path}/", parts.query, parts.fragment))
