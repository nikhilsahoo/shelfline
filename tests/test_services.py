from pathlib import Path
import base64

import httpx
import pytest
from pytest_httpx import HTTPXMock

from epub_tui.config import AppConfig, CatalogConfig
from epub_tui.downloads import DownloadError, DownloadProgress
from epub_tui.services import CatalogWorkflow


@pytest.mark.asyncio
async def test_workflow_fetches_parses_caches_and_downloads(
    tmp_path: Path,
    fixture_dir: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    httpx_mock.add_response(url="https://example.test/opds/books/sample.epub", content=b"epub bytes")

    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[CatalogConfig(name="Public", url="https://example.test/opds")],
        preferences={},
    )
    workflow = CatalogWorkflow(config=config, state_db=tmp_path / "state.db", http_client=httpx.AsyncClient())

    feed = await workflow.fetch_catalog(config.catalogs[0])
    downloaded = await workflow.download_best_epub(config.catalogs[0], feed.entries[0])

    assert feed.title == "Fiction"
    assert feed.source_url == "https://example.test/opds"
    assert workflow.library.get_feed_cache("https://example.test/opds")["body"] == feed_xml
    assert downloaded.read_bytes() == b"epub bytes"
    assert workflow.library.list_books()[0].title == "Sample Book"
    assert workflow.library.list_books()[0].authors == ["Ada Writer"]
    assert workflow.library.list_books()[0].identifiers == ["urn:isbn:9780000000001"]
    assert workflow.library.list_books()[0].source_catalog == "Public"
    assert workflow.library.list_books()[0].acquisition_url == "https://example.test/opds/books/sample.epub"
    assert workflow.library.list_books()[0].media_type == "application/epub+zip"
    assert workflow.library.list_books()[0].cover_image_url == "https://example.test/opds/covers/sample.jpg"
    assert workflow.library.list_books()[0].local_file_path == tmp_path / "books" / "Sample Book.epub"
    assert workflow.library.list_books()[0].is_read is False


@pytest.mark.asyncio
async def test_workflow_reports_waiting_status_for_outgoing_calls(
    tmp_path: Path,
    fixture_dir: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[CatalogConfig(name="Public", url="https://example.test/opds")],
        preferences={},
    )
    workflow = CatalogWorkflow(config=config, state_db=tmp_path / "state.db", http_client=httpx.AsyncClient())
    statuses: list[str] = []

    await workflow.fetch_catalog(config.catalogs[0], on_status=statuses.append)

    assert statuses == ["Fetching catalog...", "Catalog loaded"]


@pytest.mark.asyncio
async def test_workflow_uses_auth_without_exposing_credentials_in_callbacks(
    tmp_path: Path,
    fixture_dir: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")
    expected_auth = "Basic " + base64.b64encode(b"alice:secret").decode("ascii")
    httpx_mock.add_response(url="https://example.test/private", text=feed_xml)

    def download_handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == expected_auth
        return httpx.Response(200, content=b"epub bytes", headers={"content-length": "10"})

    httpx_mock.add_callback(download_handler, url="https://example.test/private/books/sample.epub")
    catalog = CatalogConfig(
        name="Private",
        url="https://example.test/private",
        auth={"username": "alice", "password": "secret"},
    )
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[catalog],
        preferences={},
    )
    workflow = CatalogWorkflow(config=config, state_db=tmp_path / "state.db", http_client=httpx.AsyncClient())
    statuses: list[str] = []
    progress: list[DownloadProgress] = []

    feed = await workflow.fetch_catalog(catalog, on_status=statuses.append)
    await workflow.download_best_epub(
        catalog,
        feed.entries[0],
        on_status=statuses.append,
        on_progress=progress.append,
    )

    assert statuses == [
        "Fetching catalog...",
        "Catalog loaded",
        "Starting download...",
        "Download complete",
    ]
    assert progress[-1] == DownloadProgress(bytes_received=10, total_bytes=10)
    assert "alice" not in " ".join(statuses)
    assert "secret" not in " ".join(statuses)


@pytest.mark.asyncio
async def test_workflow_raises_download_error_when_entry_has_no_epub(
    tmp_path: Path,
    fixture_dir: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "navigation.xml").read_text(encoding="utf-8")
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    config = AppConfig(
        library_path=tmp_path / "books",
        catalogs=[CatalogConfig(name="Public", url="https://example.test/opds")],
        preferences={},
    )
    workflow = CatalogWorkflow(config=config, state_db=tmp_path / "state.db", http_client=httpx.AsyncClient())

    feed = await workflow.fetch_catalog(config.catalogs[0])

    with pytest.raises(DownloadError, match="No EPUB acquisition link"):
        await workflow.download_best_epub(config.catalogs[0], feed.entries[0])
