from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser

from shelfline.catalog.models import AcquisitionLink, CatalogEntry, CatalogFeed

OPDS_ACQUISITION_REL = "http://opds-spec.org/acquisition"
OPDS_IMAGE_REL = "http://opds-spec.org/image"
OPDS_THUMBNAIL_REL = "http://opds-spec.org/image/thumbnail"
SUBSECTION_REL = "subsection"
OPDS_SUBSECTION_REL = "http://opds-spec.org/subsection"


class OpdsParseError(ValueError):
    pass


def parse_opds_feed(xml: str, source_url: str) -> CatalogFeed:
    source_url = sanitize_url_credentials(source_url)
    parsed = feedparser.parse(xml)
    feed_title = _get_text(parsed.feed, "title")

    if parsed.bozo or not feed_title:
        raise OpdsParseError("Invalid OPDS feed")

    return CatalogFeed(
        title=feed_title,
        source_url=source_url,
        updated=_get_optional_text(parsed.feed, "updated"),
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

        resolved_href = _resolve_link_href(source_url, href)
        if resolved_href is None:
            continue
        media_type = link.get("type", "")

        if _is_navigation_link(relation, media_type):
            navigation_url = resolved_href
        elif relation == OPDS_IMAGE_REL:
            cover_image_url = resolved_href
        elif relation == OPDS_THUMBNAIL_REL:
            thumbnail_url = resolved_href
        elif _is_acquisition_relation(relation):
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
        identifier=_get_optional_text(entry, "id"),
        updated=_get_optional_text(entry, "updated"),
        authors=[author.name for author in entry.get("authors", []) if author.get("name")],
        summary=_get_text(entry, "summary") or None,
        cover_image_url=cover_image_url,
        thumbnail_url=thumbnail_url,
        navigation_url=navigation_url,
        acquisition_links=acquisition_links,
    )


def _is_acquisition_relation(relation: str) -> bool:
    return relation == OPDS_ACQUISITION_REL or relation.startswith(f"{OPDS_ACQUISITION_REL}/")


def _resolve_link_href(source_url: str, href: str) -> str | None:
    try:
        return sanitize_url_credentials(urljoin(source_url, href))
    except ValueError:
        return None


def _is_navigation_link(relation: str, media_type: str) -> bool:
    return relation in {SUBSECTION_REL, OPDS_SUBSECTION_REL} or _is_opds_catalog_media_type(media_type)


def _is_opds_catalog_media_type(media_type: str) -> bool:
    media_type = media_type.lower()
    return "application/atom+xml" in media_type and "opds-catalog" in media_type


def _get_text(mapping: Any, key: str) -> str:
    value = mapping.get(key, "")
    return str(value).strip() if value is not None else ""


def _get_optional_text(mapping: Any, key: str) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None

    text = str(value).strip()
    return text or None


def _parse_size(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def sanitize_url_credentials(url: str) -> str:
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url

    hostname = parts.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = hostname
    if parts.port is not None:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def sanitize_text_url_credentials(text: str) -> str:
    text = re.sub(r"(https?://)[^\s\"'<>/@]+(?::[^\s\"'<>/@]*)?@", r"\1", text)
    return re.sub(r"(?<!:)(//)[^\s\"'<>/@]+(?::[^\s\"'<>/@]*)?@", r"\1", text)
