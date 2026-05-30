from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import feedparser

from epub_tui.catalog.models import AcquisitionLink, CatalogEntry, CatalogFeed

OPDS_ACQUISITION_REL = "http://opds-spec.org/acquisition"
OPDS_IMAGE_REL = "http://opds-spec.org/image"
OPDS_THUMBNAIL_REL = "http://opds-spec.org/image/thumbnail"
SUBSECTION_REL = "subsection"


class OpdsParseError(ValueError):
    pass


def parse_opds_feed(xml: str, *, source_url: str) -> CatalogFeed:
    parsed = feedparser.parse(xml)
    feed_title = _get_text(parsed.feed, "title")

    if parsed.bozo or not feed_title:
        raise OpdsParseError("Invalid OPDS feed")

    return CatalogFeed(
        title=feed_title,
        source_url=source_url,
        updated=_get_text(parsed.feed, "updated"),
        entries=[_parse_entry(entry, source_url) for entry in parsed.entries],
    )


def _parse_entry(entry: Any, source_url: str) -> CatalogEntry:
    navigation_url: str | None = None
    cover_image_url: str | None = None
    thumbnail_url: str | None = None
    acquisition_links: list[AcquisitionLink] = []

    for link in entry.get("links", []):
        relation = link.get("rel", "")
        href = link.get("href")
        if not href:
            continue

        resolved_href = urljoin(source_url, href)
        media_type = link.get("type", "")

        if relation == SUBSECTION_REL:
            navigation_url = resolved_href
        elif relation == OPDS_IMAGE_REL:
            cover_image_url = resolved_href
        elif relation == OPDS_THUMBNAIL_REL:
            thumbnail_url = resolved_href
        elif relation == OPDS_ACQUISITION_REL:
            acquisition_links.append(
                AcquisitionLink(
                    href=resolved_href,
                    relation=relation,
                    media_type=media_type,
                    title=link.get("title"),
                    size=_parse_size(link.get("length")),
                )
            )

    return CatalogEntry(
        title=_get_text(entry, "title"),
        identifier=_get_text(entry, "id"),
        updated=_get_text(entry, "updated"),
        authors=[author.name for author in entry.get("authors", []) if author.get("name")],
        summary=_get_text(entry, "summary") or None,
        cover_image_url=cover_image_url,
        thumbnail_url=thumbnail_url,
        navigation_url=navigation_url,
        acquisition_links=acquisition_links,
    )


def _get_text(mapping: Any, key: str) -> str:
    value = mapping.get(key, "")
    return str(value).strip() if value is not None else ""


def _parse_size(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
