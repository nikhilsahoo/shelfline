from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AcquisitionLink:
    href: str
    relation: str
    media_type: str
    title: str | None = None
    size: int | None = None


@dataclass
class CatalogEntry:
    title: str
    identifier: str
    updated: str
    authors: list[str] = field(default_factory=list)
    summary: str | None = None
    cover_image_url: str | None = None
    thumbnail_url: str | None = None
    navigation_url: str | None = None
    acquisition_links: list[AcquisitionLink] = field(default_factory=list)

    def best_epub_link(self) -> AcquisitionLink | None:
        for link in self.acquisition_links:
            if link.media_type == "application/epub+zip":
                return link
        return None


@dataclass
class CatalogFeed:
    title: str
    source_url: str
    updated: str
    entries: list[CatalogEntry]
