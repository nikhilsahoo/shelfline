import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from epub_tui.downloads import DownloadError, DownloadProgress, DownloadService


class CancellingStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b"partial bytes"
        raise asyncio.CancelledError


def test_download_error_is_runtime_error() -> None:
    assert isinstance(DownloadError(), RuntimeError)


def test_download_progress_percent_rounds_to_two_decimal_places() -> None:
    progress = DownloadProgress(bytes_received=1, total_bytes=6)

    assert progress.percent == 16.67


@pytest.mark.asyncio
async def test_download_service_can_use_default_client() -> None:
    service = DownloadService()

    await service.aclose()


@pytest.mark.asyncio
async def test_download_writes_temp_then_final_file(
    tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url="https://example.test/book.epub", content=b"book bytes")
    service = DownloadService(httpx.AsyncClient())

    result = await service.download(
        url="https://example.test/book.epub",
        destination_dir=tmp_path,
        filename="book.epub",
    )

    assert result == tmp_path / "book.epub"
    assert result.read_bytes() == b"book bytes"
    assert not (tmp_path / "book.epub.part").exists()


@pytest.mark.asyncio
async def test_download_rejects_duplicate_final_file(
    tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    (tmp_path / "book.epub").write_bytes(b"existing")
    service = DownloadService(httpx.AsyncClient())

    with pytest.raises(DownloadError, match="already exists"):
        await service.download(
            url="https://example.test/book.epub",
            destination_dir=tmp_path,
            filename="book.epub",
        )


@pytest.mark.asyncio
async def test_download_removes_partial_file_on_failure(
    tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(url="https://example.test/book.epub", status_code=500)
    service = DownloadService(httpx.AsyncClient())

    with pytest.raises(DownloadError, match="HTTP 500"):
        await service.download(
            url="https://example.test/book.epub",
            destination_dir=tmp_path,
            filename="book.epub",
        )

    assert not (tmp_path / "book.epub.part").exists()


@pytest.mark.asyncio
async def test_download_removes_partial_file_on_cancellation(
    tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=CancellingStream())

    httpx_mock.add_callback(handler, url="https://example.test/book.epub")
    service = DownloadService(httpx.AsyncClient())

    with pytest.raises(asyncio.CancelledError):
        await service.download(
            url="https://example.test/book.epub",
            destination_dir=tmp_path,
            filename="book.epub",
        )

    assert not (tmp_path / "book.epub.part").exists()
    assert not (tmp_path / "book.epub").exists()


@pytest.mark.asyncio
async def test_download_rejects_redirect_without_writing_final_file(
    tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="https://example.test/book.epub",
        status_code=302,
        headers={"location": "https://example.test/redirected.epub"},
        content=b"redirect body",
    )
    service = DownloadService(httpx.AsyncClient())

    with pytest.raises(DownloadError, match="HTTP 302"):
        await service.download(
            url="https://example.test/book.epub",
            destination_dir=tmp_path,
            filename="book.epub",
        )

    assert not (tmp_path / "book.epub").exists()
    assert not (tmp_path / "book.epub.part").exists()


@pytest.mark.asyncio
async def test_download_reports_progress_with_known_total(
    tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="https://example.test/book.epub",
        content=b"book",
        headers={"content-length": "4"},
    )
    service = DownloadService(httpx.AsyncClient())
    updates: list[DownloadProgress] = []

    await service.download(
        url="https://example.test/book.epub",
        destination_dir=tmp_path,
        filename="book.epub",
        on_progress=updates.append,
    )

    assert updates[-1] == DownloadProgress(bytes_received=4, total_bytes=4)
    assert updates[-1].percent == 100.0


@pytest.mark.asyncio
async def test_download_reports_progress_without_known_total(
    tmp_path: Path, httpx_mock: HTTPXMock
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(b"book"))

    httpx_mock.add_callback(handler, url="https://example.test/book.epub")
    service = DownloadService(httpx.AsyncClient())
    updates: list[DownloadProgress] = []

    await service.download(
        url="https://example.test/book.epub",
        destination_dir=tmp_path,
        filename="book.epub",
        on_progress=updates.append,
    )

    assert updates[-1] == DownloadProgress(bytes_received=4, total_bytes=None)
    assert updates[-1].percent is None
