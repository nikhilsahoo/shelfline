from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from epub_tui.downloads import DownloadError, DownloadProgress, DownloadService


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
