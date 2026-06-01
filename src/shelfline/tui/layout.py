from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Static


class ShellHeader(Static):
    def __init__(self, area: str, context: str = "", **kwargs: object) -> None:
        title = f"shelfline | {area}"
        if context:
            title = f"{title} | {context}"
        super().__init__(title, id="shell-header", **kwargs)


class KeyHintFooter(Static):
    def __init__(self, hints: str, **kwargs: object) -> None:
        super().__init__(hints, id="key-hints", **kwargs)

    def set_hints(self, hints: str) -> None:
        self.update(hints)


class AppShell(Container):
    def __init__(
        self,
        *,
        area: str,
        key_hints: str,
        context: str = "",
        **kwargs: object,
    ) -> None:
        super().__init__(id="app-shell", **kwargs)
        self.area = area
        self.context = context
        self.key_hints = key_hints

    def compose(self) -> ComposeResult:
        yield ShellHeader(self.area, self.context)
        with Horizontal(id="shell-body"):
            with Vertical(id="main-region"):
                yield Static("", id="main-placeholder")
            with Vertical(id="detail-region"):
                yield Static("", id="detail-placeholder")
        yield KeyHintFooter(self.key_hints)


def replace_region(region: Widget, *widgets: Widget) -> None:
    region.remove_children()
    region.mount(*widgets)
