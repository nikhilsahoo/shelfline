from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from ebooklib import epub
from pytest_httpx import HTTPXMock

from shelfline.covers import (
    CoverCache,
    CoverError,
    MAX_COVER_BYTES,
    cached_cover_path,
    extract_epub_cover,
)


class ChunkedStream(httpx.AsyncByteStream):
    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


def test_cached_cover_path_is_deterministic_and_safe(tmp_path: Path) -> None:
    first = cached_cover_path(tmp_path, "https://example.test/covers/A Book.jpg")
    second = cached_cover_path(tmp_path, "https://example.test/covers/A Book.jpg")

    assert first == second
    assert first.parent == tmp_path / ".shelfline" / "covers"
    assert first.suffix == ".jpg"
    assert " " not in first.name


@pytest.mark.asyncio
async def test_cover_cache_fetches_public_cover(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url="https://example.test/covers/book.jpg",
        content=b"image-bytes",
        headers={"content-type": "image/jpeg"},
    )
    async with httpx.AsyncClient() as client:
        cache = CoverCache(tmp_path, client)
        path = await cache.fetch("https://example.test/covers/book.jpg")

    assert path.read_bytes() == b"image-bytes"
    assert path.suffix == ".jpg"


@pytest.mark.asyncio
async def test_cover_cache_uses_auth_for_same_origin_cover(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"].startswith("Basic ")
        return httpx.Response(200, content=b"cover", headers={"content-type": "image/jpeg"})

    httpx_mock.add_callback(handler, url="https://example.test/covers/private.jpg")

    async with httpx.AsyncClient() as client:
        cache = CoverCache(tmp_path, client)
        path = await cache.fetch(
            "https://example.test/covers/private.jpg",
            auth=("reader", "secret"),
        )

    assert path.exists()


@pytest.mark.asyncio
async def test_cover_cache_failure_is_wrapped(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(url="https://example.test/missing.jpg", status_code=404)

    async with httpx.AsyncClient() as client:
        cache = CoverCache(tmp_path, client)
        with pytest.raises(CoverError, match="Could not fetch cover"):
            await cache.fetch("https://example.test/missing.jpg")


@pytest.mark.asyncio
async def test_cover_cache_redacts_credentials_in_failure_message(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    url = "https://reader:secret@example.test/missing.jpg"
    httpx_mock.add_response(url=url, status_code=404)

    async with httpx.AsyncClient() as client:
        cache = CoverCache(tmp_path, client)
        with pytest.raises(CoverError) as error:
            await cache.fetch(url)

    message = str(error.value)
    assert "reader" not in message
    assert "secret" not in message
    assert "https://example.test/missing.jpg" in message


@pytest.mark.asyncio
async def test_cover_cache_rejects_oversized_cover_without_writing(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url="https://example.test/covers/huge.jpg",
        content=b"x" * (MAX_COVER_BYTES + 1),
        headers={"content-type": "image/jpeg"},
    )

    async with httpx.AsyncClient() as client:
        cache = CoverCache(tmp_path, client)
        with pytest.raises(CoverError, match="too large"):
            await cache.fetch("https://example.test/covers/huge.jpg")

    assert not (tmp_path / ".shelfline" / "covers").exists()


@pytest.mark.asyncio
async def test_cover_cache_rejects_oversized_content_length_without_writing(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url="https://example.test/covers/declared-huge.jpg",
        content=b"small",
        headers={
            "content-length": str(MAX_COVER_BYTES + 1),
            "content-type": "image/jpeg",
        },
    )

    async with httpx.AsyncClient() as client:
        cache = CoverCache(tmp_path, client)
        with pytest.raises(CoverError, match="too large"):
            await cache.fetch("https://example.test/covers/declared-huge.jpg")

    assert not (tmp_path / ".shelfline" / "covers").exists()


@pytest.mark.asyncio
async def test_cover_cache_rejects_oversized_chunked_stream_without_writing(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url="https://example.test/covers/chunked-huge.jpg",
        stream=ChunkedStream([b"x" * MAX_COVER_BYTES, b"y"]),
        headers={"content-type": "image/jpeg"},
    )

    async with httpx.AsyncClient() as client:
        cache = CoverCache(tmp_path, client)
        with pytest.raises(CoverError, match="too large"):
            await cache.fetch("https://example.test/covers/chunked-huge.jpg")

    assert not (tmp_path / ".shelfline" / "covers").exists()


@pytest.mark.asyncio
async def test_cover_cache_rejects_non_image_content_type_without_writing(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url="https://example.test/covers/not-image.jpg",
        content=b"<html></html>",
        headers={"content-type": "text/html"},
    )

    async with httpx.AsyncClient() as client:
        cache = CoverCache(tmp_path, client)
        with pytest.raises(CoverError, match="not an image"):
            await cache.fetch("https://example.test/covers/not-image.jpg")

    assert not (tmp_path / ".shelfline" / "covers").exists()


@pytest.mark.asyncio
async def test_cover_cache_rejects_unsupported_image_type_without_writing(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(
        url="https://example.test/covers/vector.svg",
        content=b"<svg></svg>",
        headers={"content-type": "image/svg+xml"},
    )

    async with httpx.AsyncClient() as client:
        cache = CoverCache(tmp_path, client)
        with pytest.raises(CoverError, match="unsupported image type"):
            await cache.fetch("https://example.test/covers/vector.svg")

    assert not (tmp_path / ".shelfline" / "covers").exists()


@pytest.mark.asyncio
async def test_cover_cache_redacts_credentials_with_malformed_port() -> None:
    url = "https://reader:secret@example.test:bad/missing.jpg"

    async with httpx.AsyncClient() as client:
        cache = CoverCache(Path("."), client)
        with pytest.raises(CoverError) as error:
            await cache.fetch(url)

    message = str(error.value)
    assert "reader" not in message
    assert "secret" not in message
    assert "https://example.test:bad/missing.jpg" in message


@pytest.mark.asyncio
async def test_cover_cache_redacts_credentials_and_preserves_ipv6_brackets(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    url = "https://reader:secret@[2001:db8::1]:8443/missing.jpg"
    httpx_mock.add_response(url=url, status_code=404)

    async with httpx.AsyncClient() as client:
        cache = CoverCache(tmp_path, client)
        with pytest.raises(CoverError) as error:
            await cache.fetch(url)

    message = str(error.value)
    assert "reader" not in message
    assert "secret" not in message
    assert "https://[2001:db8::1]:8443/missing.jpg" in message


def test_extract_epub_cover_returns_none_without_cover(tmp_path: Path) -> None:
    epub_path = tmp_path / "empty.epub"
    epub_path.write_bytes(b"not an epub")

    assert extract_epub_cover(epub_path, tmp_path) is None


def test_extract_epub_cover_caches_embedded_cover(tmp_path: Path) -> None:
    epub_path = tmp_path / "covered.epub"
    cover_bytes = b"cover-image-bytes"
    book = epub.EpubBook()
    book.set_identifier("covered")
    book.set_title("Covered")
    book.set_language("en")
    book.set_cover("cover.jpg", cover_bytes)
    chapter = epub.EpubHtml(title="Chapter", file_name="chapter.xhtml", lang="en")
    chapter.content = b"<html><body><p>Text.</p></body></html>"
    book.add_item(chapter)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)

    path = extract_epub_cover(epub_path, tmp_path)

    assert path is not None
    assert path.parent == tmp_path / ".shelfline" / "covers"
    assert path.suffix == ".jpg"
    assert path.read_bytes() == cover_bytes


def test_extract_epub_cover_falls_back_for_weird_embedded_suffix(tmp_path: Path) -> None:
    epub_path = tmp_path / "weird-cover.epub"
    cover_bytes = b"cover-image-bytes"
    book = epub.EpubBook()
    book.set_identifier("weird-cover")
    book.set_title("Weird Cover")
    book.set_language("en")
    cover = epub.EpubImage(
        uid="cover",
        file_name="images/cover.not-image",
        media_type="image/jpeg",
        content=cover_bytes,
    )
    book.add_item(cover)
    chapter = epub.EpubHtml(title="Chapter", file_name="chapter.xhtml", lang="en")
    chapter.content = b"<html><body><p>Text.</p></body></html>"
    book.add_item(chapter)
    book.spine = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)

    path = extract_epub_cover(epub_path, tmp_path)

    assert path is not None
    assert path.suffix == ".jpg"
    assert path.read_bytes() == cover_bytes


def test_extract_epub_cover_uses_media_type_fallback_for_weird_embedded_suffix(
    tmp_path: Path,
) -> None:
    epub_path = tmp_path / "weird-png-cover.epub"
    cover_bytes = b"cover-image-bytes"
    book = epub.EpubBook()
    book.set_identifier("weird-png-cover")
    book.set_title("Weird Png Cover")
    book.set_language("en")
    cover = epub.EpubImage(
        uid="cover",
        file_name="images/cover.not-image",
        media_type="image/png",
        content=cover_bytes,
    )
    book.add_item(cover)
    chapter = epub.EpubHtml(title="Chapter", file_name="chapter.xhtml", lang="en")
    chapter.content = b"<html><body><p>Text.</p></body></html>"
    book.add_item(chapter)
    book.spine = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)

    path = extract_epub_cover(epub_path, tmp_path)

    assert path is not None
    assert path.suffix == ".png"
    assert path.read_bytes() == cover_bytes


def test_extract_epub_cover_skips_oversized_candidate_and_uses_later_valid_cover(
    tmp_path: Path,
) -> None:
    epub_path = tmp_path / "oversized-cover.epub"
    valid_cover_bytes = b"valid-cover"
    book = epub.EpubBook()
    book.set_identifier("oversized-cover")
    book.set_title("Oversized Cover")
    book.set_language("en")
    book.add_item(
        epub.EpubImage(
            uid="cover-huge",
            file_name="images/cover-huge.jpg",
            media_type="image/jpeg",
            content=b"x" * (MAX_COVER_BYTES + 1),
        )
    )
    book.add_item(
        epub.EpubImage(
            uid="cover-valid",
            file_name="images/cover-valid.jpg",
            media_type="image/jpeg",
            content=valid_cover_bytes,
        )
    )
    chapter = epub.EpubHtml(title="Chapter", file_name="chapter.xhtml", lang="en")
    chapter.content = b"<html><body><p>Text.</p></body></html>"
    book.add_item(chapter)
    book.spine = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)

    path = extract_epub_cover(epub_path, tmp_path)

    assert path is not None
    assert path.suffix == ".jpg"
    assert path.read_bytes() == valid_cover_bytes


def test_extract_epub_cover_skips_unsupported_candidate_and_uses_later_valid_cover(
    tmp_path: Path,
) -> None:
    epub_path = tmp_path / "unsupported-cover.epub"
    valid_cover_bytes = b"valid-cover"
    book = epub.EpubBook()
    book.set_identifier("unsupported-cover")
    book.set_title("Unsupported Cover")
    book.set_language("en")
    book.add_item(
        epub.EpubImage(
            uid="cover-svg",
            file_name="images/cover.svg",
            media_type="image/svg+xml",
            content=b"<svg></svg>",
        )
    )
    book.add_item(
        epub.EpubImage(
            uid="cover-valid",
            file_name="images/cover-valid.png",
            media_type="image/png",
            content=valid_cover_bytes,
        )
    )
    chapter = epub.EpubHtml(title="Chapter", file_name="chapter.xhtml", lang="en")
    chapter.content = b"<html><body><p>Text.</p></body></html>"
    book.add_item(chapter)
    book.spine = [chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(epub_path), book)

    path = extract_epub_cover(epub_path, tmp_path)

    assert path is not None
    assert path.suffix == ".png"
    assert path.read_bytes() == valid_cover_bytes
