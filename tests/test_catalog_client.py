import base64

import httpx
import pytest
from pytest_httpx import HTTPXMock

from epub_tui.catalog.client import CatalogClient, CatalogFetchError
from epub_tui.config import CatalogConfig


@pytest.mark.asyncio
async def test_fetch_feed_without_auth(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://example.test/opds", text="<feed><title>Hi</title></feed>")
    client = CatalogClient(httpx.AsyncClient())

    text = await client.fetch_feed(CatalogConfig(name="Public", url="https://example.test/opds"))

    assert "<title>Hi</title>" in text


@pytest.mark.asyncio
async def test_fetch_feed_with_basic_auth(httpx_mock: HTTPXMock) -> None:
    expected = "Basic " + base64.b64encode(b"alice:secret").decode("ascii")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == expected
        return httpx.Response(200, text="<feed><title>Private</title></feed>")

    httpx_mock.add_callback(handler, url="https://example.test/private")
    client = CatalogClient(httpx.AsyncClient())

    text = await client.fetch_feed(
        CatalogConfig(
            name="Private",
            url="https://example.test/private",
            auth={"username": "alice", "password": "secret"},
        )
    )

    assert "Private" in text


@pytest.mark.asyncio
async def test_fetch_feed_redacts_password_on_error(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://example.test/private", status_code=401)
    client = CatalogClient(httpx.AsyncClient())

    with pytest.raises(CatalogFetchError) as exc:
        await client.fetch_feed(
            CatalogConfig(
                name="Private",
                url="https://example.test/private",
                auth={"username": "alice", "password": "secret"},
            )
        )

    assert "secret" not in str(exc.value)
    assert "Authentication failed for catalog Private" in str(exc.value)
