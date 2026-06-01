from pathlib import Path
import base64

import httpx
import pytest
from pytest_httpx import HTTPXMock

from shelfline.config import AppConfig, CatalogConfig, load_config
from shelfline.credentials import CredentialStore, MemoryCredentialBackend
from shelfline.downloads import DownloadError, DownloadProgress
from shelfline.services import CatalogWorkflow


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
async def test_workflow_resolves_password_ref_for_same_origin_fetch_and_download(
    tmp_path: Path,
    fixture_dir: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")
    expected_auth = "Basic " + base64.b64encode(b"alice:secret").decode("ascii")
    store = CredentialStore(MemoryCredentialBackend())
    store.save_password("Private", "alice", "secret")

    def assert_authorized(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == expected_auth
        if request.url.path.endswith(".epub"):
            return httpx.Response(200, content=b"epub bytes")
        return httpx.Response(200, text=feed_xml)

    catalog = CatalogConfig(
        name="Private",
        url="https://example.test/private",
        auth={"username": "alice", "password_ref": "shelfline:Private"},
    )
    workflow = CatalogWorkflow(
        config=AppConfig(library_path=tmp_path / "books", catalogs=[catalog], preferences={}),
        state_db=tmp_path / "state.db",
        http_client=httpx.AsyncClient(),
        credentials=store,
    )
    httpx_mock.add_callback(assert_authorized, url="https://example.test/private")
    httpx_mock.add_callback(assert_authorized, url="https://example.test/private/books/sample.epub")

    feed = await workflow.fetch_catalog(catalog)
    downloaded = await workflow.download_best_epub(catalog, feed.entries[0])

    assert downloaded.read_bytes() == b"epub bytes"


@pytest.mark.asyncio
async def test_workflow_omits_auth_when_password_ref_lookup_misses(
    tmp_path: Path,
    fixture_dir: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")
    store = CredentialStore(MemoryCredentialBackend())

    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, text=feed_xml)

    catalog = CatalogConfig(
        name="Private",
        url="https://example.test/private",
        auth={"username": "alice", "password_ref": "shelfline:Private"},
    )
    workflow = CatalogWorkflow(
        config=AppConfig(library_path=tmp_path / "books", catalogs=[catalog], preferences={}),
        state_db=tmp_path / "state.db",
        http_client=httpx.AsyncClient(),
        credentials=store,
    )
    httpx_mock.add_callback(handler, url="https://example.test/private")

    feed = await workflow.fetch_catalog(catalog)

    assert feed.title == "Fiction"


@pytest.mark.asyncio
async def test_workflow_fetch_omits_auth_for_cross_origin_override(
    tmp_path: Path,
    fixture_dir: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")

    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, text=feed_xml)

    httpx_mock.add_callback(handler, url="https://other.test/opds")
    catalog = CatalogConfig(
        name="Private",
        url="https://example.test/opds",
        auth={"username": "alice", "password": "secret"},
    )
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books", catalogs=[catalog], preferences={}),
        tmp_path / "state.db",
        httpx.AsyncClient(),
    )

    feed = await workflow.fetch_catalog(catalog, url="https://other.test/opds")

    assert feed.source_url == "https://other.test/opds"


@pytest.mark.asyncio
async def test_workflow_fetch_sends_auth_for_same_origin_override(
    tmp_path: Path,
    fixture_dir: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = (fixture_dir / "opds" / "acquisition.xml").read_text(encoding="utf-8")
    expected_auth = "Basic " + base64.b64encode(b"alice:secret").decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == expected_auth
        return httpx.Response(200, text=feed_xml)

    httpx_mock.add_callback(handler, url="https://example.test/alternate")
    catalog = CatalogConfig(
        name="Private",
        url="https://example.test/opds",
        auth={"username": "alice", "password": "secret"},
    )
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books", catalogs=[catalog], preferences={}),
        tmp_path / "state.db",
        httpx.AsyncClient(),
    )

    feed = await workflow.fetch_catalog(catalog, url="https://example.test/alternate")

    assert feed.source_url == "https://example.test/alternate"


@pytest.mark.asyncio
async def test_workflow_download_omits_auth_for_cross_origin_acquisition(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Private</title>
  <entry>
    <title>Remote Book</title>
    <link rel="http://opds-spec.org/acquisition" href="https://cdn.test/remote.epub" type="application/epub+zip"/>
  </entry>
</feed>
"""
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, content=b"epub bytes")

    httpx_mock.add_callback(handler, url="https://cdn.test/remote.epub")
    catalog = CatalogConfig(
        name="Private",
        url="https://example.test/opds",
        auth={"username": "alice", "password": "secret"},
    )
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books", catalogs=[catalog], preferences={}),
        tmp_path / "state.db",
        httpx.AsyncClient(),
    )

    feed = await workflow.fetch_catalog(catalog)
    downloaded = await workflow.download_best_epub(catalog, feed.entries[0])

    assert downloaded.read_bytes() == b"epub bytes"


@pytest.mark.asyncio
async def test_workflow_stores_sanitized_acquisition_url_from_embedded_credentials(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        """
{
  "library_path": "%s",
  "catalogs": [
    {
      "name": "Private",
      "url": "https://alice:secret@example.test/opds"
    }
  ]
}
"""
        % str(tmp_path / "books").replace("\\", "\\\\"),
        encoding="utf-8",
    )
    feed_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Private</title>
  <entry>
    <title>Private Book</title>
    <link rel="http://opds-spec.org/acquisition" href="books/private.epub" type="application/epub+zip"/>
  </entry>
</feed>
"""
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    httpx_mock.add_response(url="https://example.test/opds/books/private.epub", content=b"epub bytes")
    config = load_config(config_path)
    catalog = config.catalogs[0]
    workflow = CatalogWorkflow(config=config, state_db=tmp_path / "state.db", http_client=httpx.AsyncClient())

    feed = await workflow.fetch_catalog(catalog)
    await workflow.download_best_epub(catalog, feed.entries[0])

    book = workflow.library.list_books()[0]
    assert book.acquisition_url == "https://example.test/opds/books/private.epub"
    assert "alice" not in book.acquisition_url
    assert "secret" not in book.acquisition_url


@pytest.mark.asyncio
async def test_workflow_stores_sanitized_cover_metadata_from_credentialed_opds_link(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Private</title>
  <entry>
    <title>Private Book</title>
    <link rel="http://opds-spec.org/image" href="https://alice:secret@example.test/covers/private.jpg"/>
    <link rel="http://opds-spec.org/acquisition" href="books/private.epub" type="application/epub+zip"/>
  </entry>
</feed>
"""
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    httpx_mock.add_response(url="https://example.test/opds/books/private.epub", content=b"epub bytes")
    catalog = CatalogConfig(name="Private", url="https://example.test/opds")
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books", catalogs=[catalog], preferences={}),
        tmp_path / "state.db",
        httpx.AsyncClient(),
    )

    feed = await workflow.fetch_catalog(catalog)
    await workflow.download_best_epub(catalog, feed.entries[0])

    book = workflow.library.list_books()[0]
    assert book.cover_image_url == "https://example.test/covers/private.jpg"
    assert "alice" not in book.cover_image_url
    assert "secret" not in book.cover_image_url


@pytest.mark.asyncio
async def test_workflow_feed_cache_body_strips_credentialed_links(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Private</title>
  <entry>
    <title>Private Book</title>
    <link rel="http://opds-spec.org/image" href="https://alice:secret@example.test/covers/private.jpg"/>
    <link rel="http://opds-spec.org/acquisition" href="https://alice:secret@example.test/books/private.epub" type="application/epub+zip"/>
  </entry>
</feed>
"""
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    catalog = CatalogConfig(name="Private", url="https://example.test/opds")
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books", catalogs=[catalog], preferences={}),
        tmp_path / "state.db",
        httpx.AsyncClient(),
    )

    await workflow.fetch_catalog(catalog)

    cached = workflow.library.get_feed_cache("https://example.test/opds")
    assert cached is not None
    assert "alice" not in cached["body"]
    assert "secret" not in cached["body"]
    assert "https://example.test/books/private.epub" in cached["body"]


@pytest.mark.asyncio
async def test_workflow_feed_cache_body_strips_network_path_credentials(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Private</title>
  <entry>
    <title>Private Book</title>
    <link rel="http://opds-spec.org/acquisition" href="//alice:secret@example.test/books/private.epub" type="application/epub+zip"/>
  </entry>
</feed>
"""
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    catalog = CatalogConfig(name="Private", url="https://example.test/opds")
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books", catalogs=[catalog], preferences={}),
        tmp_path / "state.db",
        httpx.AsyncClient(),
    )

    await workflow.fetch_catalog(catalog)

    cached = workflow.library.get_feed_cache("https://example.test/opds")
    assert cached is not None
    assert "alice" not in cached["body"]
    assert "secret" not in cached["body"]
    assert "//example.test/books/private.epub" in cached["body"]


@pytest.mark.asyncio
async def test_workflow_downloads_and_tracks_non_epub_acquisition(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Private</title>
  <entry>
    <title>Scanned Book</title>
    <id>urn:example:scanned</id>
    <author><name>Casey Archivist</name></author>
    <link rel="http://opds-spec.org/acquisition" href="downloads/scanned" type="application/pdf" title="PDF"/>
  </entry>
</feed>
"""
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    httpx_mock.add_response(url="https://example.test/opds/downloads/scanned", content=b"pdf bytes")
    catalog = CatalogConfig(name="Public", url="https://example.test/opds")
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books", catalogs=[catalog], preferences={}),
        tmp_path / "state.db",
        httpx.AsyncClient(),
    )

    feed = await workflow.fetch_catalog(catalog)
    downloaded = await workflow.download_acquisition(catalog, feed.entries[0])

    assert downloaded == tmp_path / "books" / "Scanned Book.pdf"
    assert downloaded.read_bytes() == b"pdf bytes"
    book = workflow.library.list_books()[0]
    assert book.title == "Scanned Book"
    assert book.authors == ["Casey Archivist"]
    assert book.identifiers == ["urn:example:scanned"]
    assert book.acquisition_url == "https://example.test/opds/downloads/scanned"
    assert book.media_type == "application/pdf"
    assert book.local_file_path == downloaded


@pytest.mark.asyncio
async def test_workflow_uses_safe_filename_for_windows_reserved_title(
    tmp_path: Path,
    httpx_mock: HTTPXMock,
) -> None:
    feed_xml = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Private</title>
  <entry>
    <title>CON</title>
    <link rel="http://opds-spec.org/acquisition" href="book.epub" type="application/epub+zip"/>
  </entry>
</feed>
"""
    httpx_mock.add_response(url="https://example.test/opds", text=feed_xml)
    httpx_mock.add_response(url="https://example.test/opds/book.epub", content=b"epub bytes")
    catalog = CatalogConfig(name="Private", url="https://example.test/opds")
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books", catalogs=[catalog], preferences={}),
        tmp_path / "state.db",
        httpx.AsyncClient(),
    )

    feed = await workflow.fetch_catalog(catalog)
    downloaded = await workflow.download_best_epub(catalog, feed.entries[0])

    assert downloaded.name == "book.epub"


def test_workflow_default_client_matches_service_http_defaults(tmp_path: Path) -> None:
    workflow = CatalogWorkflow(
        AppConfig(library_path=tmp_path / "books", catalogs=[], preferences={}),
        tmp_path / "state.db",
    )

    assert workflow._http_client.follow_redirects is True
    assert workflow._http_client.timeout == httpx.Timeout(60.0)


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
