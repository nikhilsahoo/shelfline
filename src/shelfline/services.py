from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

import httpx

from shelfline.catalog.client import CatalogClient
from shelfline.catalog.models import AcquisitionLink, CatalogEntry, CatalogFeed
from shelfline.catalog.parser import parse_opds_feed, sanitize_text_url_credentials, sanitize_url_credentials
from shelfline.config import AppConfig, CatalogConfig
from shelfline.covers import CoverCache, CoverError, extract_epub_cover
from shelfline.credentials import CredentialStore
from shelfline.downloads import DownloadError, DownloadProgress, DownloadService
from shelfline.library import BookRecord, LibraryRepository


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
        credentials: CredentialStore | None = None,
    ) -> None:
        self.config = config
        self._credentials = credentials or CredentialStore()
        self._http_client = http_client or httpx.AsyncClient(
            timeout=60.0,
            follow_redirects=True,
        )
        self._catalog_client = CatalogClient(self._http_client)
        self._download_service = DownloadService(self._http_client)
        self._cover_cache = CoverCache(config.library_path, self._http_client)
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
            _catalog_for_url(catalog, target_url, self._credentials),
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
            auth=_auth_tuple(catalog, self._credentials) if _same_origin(catalog.url, href) else None,
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
                thumbnail_url=entry.thumbnail_url,
                cover_image_path=None,
                local_file_path=downloaded_path,
                is_read=False,
            )
        )
        cover_path, cover_status = await self._cache_downloaded_book_cover(
            catalog,
            entry,
            downloaded_path,
            selected_link,
        )
        self.library.update_cover_cache(downloaded_path, cover_path, cover_status)
        _emit(on_status, "Download complete")
        return downloaded_path

    async def aclose(self) -> None:
        await self._http_client.aclose()

    async def _cache_downloaded_book_cover(
        self,
        catalog: CatalogConfig,
        entry: CatalogEntry,
        downloaded_path: Path,
        selected_link: AcquisitionLink,
    ) -> tuple[Path | None, str]:
        if _cover_cache_disabled(self.config):
            return None, "skipped"

        remote_url = entry.cover_image_url or entry.thumbnail_url
        remote_failed = False
        if remote_url is not None:
            try:
                return (
                    await self._cover_cache.fetch(
                        remote_url,
                        auth=_auth_tuple(catalog, self._credentials)
                        if _same_origin(catalog.url, remote_url)
                        else None,
                    ),
                    "cached",
                )
            except (CoverError, OSError):
                remote_failed = True

        if selected_link.media_type == "application/epub+zip":
            try:
                embedded_cover_path = extract_epub_cover(downloaded_path, self.config.library_path)
            except Exception:
                embedded_cover_path = None
            if embedded_cover_path is not None:
                return embedded_cover_path, "cached"

        if remote_failed:
            return None, "failed"
        return None, "missing"


def _emit(callback: StatusCallback | None, message: str) -> None:
    if callback is not None:
        callback(message)


def _cover_cache_disabled(config: AppConfig) -> bool:
    preferences = config.preferences
    covers = getattr(preferences, "covers", None)
    return getattr(covers, "display", "auto") == "off"


def _auth_tuple(
    catalog: CatalogConfig,
    credentials: CredentialStore | None = None,
) -> tuple[str, str] | None:
    if catalog.auth is None:
        return None
    username = catalog.auth.get("username")
    if not username:
        return None
    password = catalog.auth.get("password")
    if password is None:
        password_ref = catalog.auth.get("password_ref")
        if password_ref is not None and credentials is not None:
            try:
                password = credentials.backend.get_password(password_ref, username)
            except Exception:
                password = None
    if password is None:
        return None
    return username, password


def _catalog_for_url(
    catalog: CatalogConfig,
    url: str,
    credentials: CredentialStore | None = None,
) -> CatalogConfig:
    if catalog.auth is None:
        return replace(catalog, url=sanitize_url_credentials(catalog.url))
    if _same_origin(catalog.url, url):
        auth = _auth_tuple(catalog, credentials)
        if auth is None:
            return replace(catalog, url=sanitize_url_credentials(catalog.url), auth=None)
        return replace(
            catalog,
            url=sanitize_url_credentials(catalog.url),
            auth={"username": auth[0], "password": auth[1]},
        )
    return replace(catalog, auth=None)


def _same_origin(left_url: str, right_url: str) -> bool:
    try:
        left = urlsplit(left_url)
        right = urlsplit(right_url)
        return (
            left.scheme == right.scheme
            and left.hostname == right.hostname
            and _origin_port(left) == _origin_port(right)
        )
    except ValueError:
        return False


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
