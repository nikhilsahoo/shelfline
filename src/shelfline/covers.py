from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit

import httpx
from ebooklib import ITEM_COVER, ITEM_IMAGE, epub


class CoverError(RuntimeError):
    """Raised when a remote cover cannot be cached."""


_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_COVER_BYTES = 5 * 1024 * 1024


def cover_cache_dir(library_path: Path) -> Path:
    return Path(library_path) / ".shelfline" / "covers"


def cached_cover_path(
    library_path: Path,
    source_url: str,
    content_type: str | None = None,
) -> Path:
    extension = _extension_for_cover(source_url, content_type)
    digest = sha256(source_url.encode("utf-8")).hexdigest()[:24]
    return cover_cache_dir(library_path) / f"{digest}{extension}"


class CoverCache:
    def __init__(self, library_path: Path, http_client: httpx.AsyncClient) -> None:
        self.library_path = Path(library_path)
        self.http_client = http_client

    async def fetch(
        self,
        source_url: str,
        *,
        auth: tuple[str, str] | None = None,
    ) -> Path:
        try:
            response = await self.http_client.get(source_url, auth=auth)
            response.raise_for_status()
        except Exception as exc:
            safe_url = _redact_url_credentials(source_url)
            raise CoverError(f"Could not fetch cover from {safe_url}") from exc

        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        self._validate_response(source_url, response.content, content_type)
        path = cached_cover_path(self.library_path, source_url, content_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        return path

    def _validate_response(
        self,
        source_url: str,
        content: bytes,
        content_type: str,
    ) -> None:
        safe_url = _redact_url_credentials(source_url)
        if not _is_image_content_type(content_type):
            raise CoverError(f"Cover response from {safe_url} is not an image")
        if len(content) > MAX_COVER_BYTES:
            raise CoverError(f"Cover response from {safe_url} is too large")


def extract_epub_cover(epub_path: Path, library_path: Path) -> Path | None:
    try:
        book = epub.read_epub(str(epub_path))
    except Exception:
        return None

    for item in book.get_items():
        if item.get_type() not in {ITEM_COVER, ITEM_IMAGE}:
            continue
        name = item.get_name().lower()
        if "cover" not in name and item.get_type() != ITEM_COVER:
            continue

        extension = Path(name).suffix.lower() or ".jpg"
        digest = sha256(f"{epub_path}:{name}".encode("utf-8")).hexdigest()[:24]
        path = cover_cache_dir(library_path) / f"{digest}{extension}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(item.get_content())
        return path

    return None


def _extension_for_cover(source_url: str, content_type: str | None) -> str:
    if content_type:
        extension = _CONTENT_TYPE_EXTENSIONS.get(content_type.lower())
        if extension is not None:
            return extension

    suffix = Path(urlparse(source_url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def _is_image_content_type(content_type: str) -> bool:
    return content_type.startswith("image/") or content_type in _CONTENT_TYPE_EXTENSIONS


def _redact_url_credentials(source_url: str) -> str:
    try:
        parsed = urlsplit(source_url)
    except ValueError:
        return _redact_unparsed_url(source_url)

    netloc = _redact_netloc_credentials(parsed.netloc)
    return urlunsplit(parsed._replace(netloc=netloc))


def _redact_unparsed_url(source_url: str) -> str:
    scheme_separator = "://"
    if scheme_separator not in source_url:
        return source_url

    scheme, rest = source_url.split(scheme_separator, 1)
    netloc, separator, path = rest.partition("/")
    safe_netloc = _redact_netloc_credentials(netloc)
    return f"{scheme}{scheme_separator}{safe_netloc}{separator}{path}"


def _redact_netloc_credentials(netloc: str) -> str:
    if "@" not in netloc:
        return netloc
    return netloc.rsplit("@", 1)[1]
