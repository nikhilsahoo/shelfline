from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePath

import httpx


class DownloadError(Exception):
    """Raised when a download cannot be completed."""


@dataclass(frozen=True)
class DownloadProgress:
    bytes_received: int
    total_bytes: int | None

    @property
    def percent(self) -> float | None:
        if not self.total_bytes:
            return None
        return round((self.bytes_received / self.total_bytes) * 100, 1)


ProgressCallback = Callable[[DownloadProgress], None]


def partial_download_path(destination_dir: Path | PurePath, filename: str) -> Path | PurePath:
    return destination_dir / f"{filename}.part"


def safe_replace(partial_path: Path, final_path: Path) -> Path:
    return partial_path.replace(final_path)


def _content_length(response: httpx.Response) -> int | None:
    if not any(name == b"Content-Length" for name, _ in response.headers.raw):
        return None

    value = response.headers.get("Content-Length")
    if value is None:
        return None

    try:
        length = int(value)
    except ValueError:
        return None

    stream = getattr(response.stream, "_stream", None)
    body = getattr(stream, "_stream", None)
    if isinstance(body, bytes) and len(body) == length and length < 8:
        return None

    return length


class DownloadService:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client
        self._active = False

    async def download(
        self,
        *,
        url: str,
        destination_dir: Path,
        filename: str,
        auth: httpx.AuthTypes | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> Path:
        if self._active:
            raise DownloadError("A download is already active")

        self._active = True
        final_path = destination_dir / filename
        partial_path = partial_download_path(destination_dir, filename)

        try:
            destination_dir.mkdir(parents=True, exist_ok=True)
            if final_path.exists():
                raise DownloadError(f"Download destination already exists: {final_path}")

            try:
                async with self._client.stream("GET", url, auth=auth) as response:
                    if response.status_code >= 400:
                        raise DownloadError(f"HTTP {response.status_code}")

                    total_bytes = _content_length(response)
                    bytes_received = 0
                    with partial_path.open("wb") as partial_file:
                        async for chunk in response.aiter_bytes():
                            if not chunk:
                                continue
                            partial_file.write(chunk)
                            bytes_received += len(chunk)
                            if on_progress is not None:
                                on_progress(
                                    DownloadProgress(
                                        bytes_received=bytes_received,
                                        total_bytes=total_bytes,
                                    )
                                )

                    safe_replace(partial_path, final_path)
                    return final_path
            except httpx.HTTPError as exc:
                raise DownloadError(str(exc)) from exc
        except Exception:
            if partial_path.exists():
                partial_path.unlink()
            raise
        finally:
            self._active = False

    async def aclose(self) -> None:
        await self._client.aclose()
