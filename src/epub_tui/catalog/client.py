from __future__ import annotations

import httpx

from epub_tui.config import CatalogConfig


class CatalogFetchError(RuntimeError):
    pass


class CatalogClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(timeout=20.0, follow_redirects=True)

    async def fetch_feed(self, catalog: CatalogConfig, url: str | None = None) -> str:
        target_url = url or catalog.url
        try:
            response = await self._client.get(target_url, auth=_auth_tuple(catalog))
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in {401, 403}:
                raise CatalogFetchError(f"Authentication failed for catalog {catalog.name}") from exc
            raise CatalogFetchError(f"Failed to fetch catalog {catalog.name}: HTTP {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise CatalogFetchError(f"Failed to fetch catalog {catalog.name}: {exc.__class__.__name__}") from exc
        return response.text

    async def aclose(self) -> None:
        await self._client.aclose()


def _auth_tuple(catalog: CatalogConfig) -> tuple[str, str] | None:
    if catalog.auth is None:
        return None
    return catalog.auth["username"], catalog.auth["password"]
