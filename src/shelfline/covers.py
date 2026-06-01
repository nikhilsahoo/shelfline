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
            async with self.http_client.stream("GET", source_url, auth=auth) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
                self._validate_response_headers(source_url, response.headers, content_type)
                content = await self._read_cover_content(source_url, response)
        except Exception as exc:
            if isinstance(exc, CoverError):
                raise
            safe_url = _redact_url_credentials(source_url)
            raise CoverError(f"Could not fetch cover from {safe_url}") from exc

        path = cached_cover_path(self.library_path, source_url, content_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _validate_response_headers(
        self,
        source_url: str,
        headers: httpx.Headers,
        content_type: str,
    ) -> None:
        safe_url = _redact_url_credentials(source_url)
        if content_type not in _CONTENT_TYPE_EXTENSIONS:
            if content_type.startswith("image/"):
                raise CoverError(f"Cover response from {safe_url} has unsupported image type")
            raise CoverError(f"Cover response from {safe_url} is not an image")

        content_length = headers.get("content-length")
        if content_length is not None and _content_length_exceeds_limit(content_length):
            raise CoverError(f"Cover response from {safe_url} is too large")

    async def _read_cover_content(
        self,
        source_url: str,
        response: httpx.Response,
    ) -> bytes:
        safe_url = _redact_url_credentials(source_url)
        content = bytearray()
        async for chunk in response.aiter_bytes():
            content.extend(chunk)
            if len(content) > MAX_COVER_BYTES:
                raise CoverError(f"Cover response from {safe_url} is too large")
        return bytes(content)


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

        extension = _safe_image_extension(Path(name).suffix.lower())
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


def _content_length_exceeds_limit(content_length: str) -> bool:
    try:
        return int(content_length) > MAX_COVER_BYTES
    except ValueError:
        return False


def _safe_image_extension(suffix: str) -> str:
    if suffix == ".jpeg":
        return ".jpg"
    if suffix in {".jpg", ".png", ".webp", ".gif"}:
        return suffix
    return ".jpg"


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
