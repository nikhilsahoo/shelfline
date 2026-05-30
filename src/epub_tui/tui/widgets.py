from __future__ import annotations

from pathlib import Path

from textual.widgets import Static

from epub_tui.downloads import DownloadProgress


class BusyIndicator(Static):
    """Small status widget used while a screen waits on outgoing work."""

    def __init__(self, message: str = "", **kwargs: object) -> None:
        super().__init__(message, **kwargs)
        self._renderable = message

    @property
    def renderable(self) -> str:
        return self._renderable

    def start(self, message: str) -> None:
        self._renderable = message
        self.update(message)

    def stop(self) -> None:
        self._renderable = ""
        self.update("")


class StatusLine(Static):
    def __init__(self, message: str = "Ready", **kwargs: object) -> None:
        super().__init__(message, **kwargs)
        self._renderable = message

    @property
    def renderable(self) -> str:
        return self._renderable

    def set_message(self, message: str) -> None:
        self._renderable = message
        self.update(message)


class DownloadProgressDisplay(Static):
    def __init__(self, progress: DownloadProgress | None = None, **kwargs: object) -> None:
        super().__init__("", **kwargs)
        self._renderable = ""
        if progress is None:
            self._set_text("No download active")
        else:
            self.update_progress(progress)

    @property
    def renderable(self) -> str:
        return self._renderable

    def update_progress(self, progress: DownloadProgress) -> None:
        if progress.total_bytes:
            percent = int(progress.percent or 0)
            self._set_text(f"{percent}% ({progress.bytes_received}/{progress.total_bytes} bytes)")
            return

        self._set_text(f"{progress.bytes_received} bytes received (indeterminate)")

    def _set_text(self, text: str) -> None:
        self._renderable = text
        self.update(text)


class CoverDisplay(Static):
    def __init__(
        self,
        *,
        title: str,
        authors: list[str] | tuple[str, ...] | None = None,
        image_path: str | Path | None = None,
        terminal_graphics: bool = False,
        **kwargs: object,
    ) -> None:
        self.title = title
        self.authors = list(authors or [])
        self.image_path = Path(image_path) if image_path is not None else None
        self.terminal_graphics = terminal_graphics
        renderable = self._render_cover()
        super().__init__(renderable, **kwargs)
        self._renderable = renderable

    @property
    def renderable(self) -> str:
        return self._renderable

    def _render_cover(self) -> str:
        if self.terminal_graphics and self.image_path is not None and self.image_path.exists():
            return str(self.image_path)

        author_text = ", ".join(self.authors) if self.authors else "Unknown author"
        return f"{self.title}\n{author_text}"
