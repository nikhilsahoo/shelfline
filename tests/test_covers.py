from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from shelfline.covers import (
    CoverCache,
    CoverError,
    cached_cover_path,
    extract_epub_cover,
)


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
    cache = CoverCache(tmp_path, httpx.AsyncClient())

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
    cache = CoverCache(tmp_path, httpx.AsyncClient())

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
    cache = CoverCache(tmp_path, httpx.AsyncClient())

    with pytest.raises(CoverError, match="Could not fetch cover"):
        await cache.fetch("https://example.test/missing.jpg")


def test_extract_epub_cover_returns_none_without_cover(tmp_path: Path) -> None:
    epub_path = tmp_path / "empty.epub"
    epub_path.write_bytes(b"not an epub")

    assert extract_epub_cover(epub_path, tmp_path) is None
