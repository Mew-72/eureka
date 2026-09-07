"""Provider-independent search result deduplication and ranking."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from models import SearchResult

_TRACKING_PARAMETERS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def normalize_url(url: str) -> str:
    """Build a comparison key without changing the evidence URL that is stored."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.port and not (
        (parts.scheme.lower() == "http" and parts.port == 80)
        or (parts.scheme.lower() == "https" and parts.port == 443)
    ):
        host = f"{host}:{parts.port}"

    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in _TRACKING_PARAMETERS
    ]
    path = parts.path or "/"
    return urlunsplit(
        (parts.scheme.lower(), host, path, urlencode(sorted(query)), "")
    )


def merge_and_rank(*provider_results: Iterable[SearchResult]) -> list[SearchResult]:
    """Merge providers, deduplicate page URLs, and rank by provider score."""
    by_page: dict[str, SearchResult] = {}

    for results in provider_results:
        for result in results:
            key = normalize_url(result.page_url)
            existing = by_page.get(key)
            if existing is None:
                by_page[key] = result
                continue

            sources = "+".join(
                sorted(set(existing.source.split("+")) | set(result.source.split("+")))
            )
            winner = result if result.score > existing.score else existing
            image_url = winner.image_url or existing.image_url or result.image_url
            title = winner.title or existing.title or result.title
            by_page[key] = replace(
                winner,
                image_url=image_url,
                title=title,
                source=sources,
                score=max(existing.score, result.score),
            )

    return sorted(
        by_page.values(),
        key=lambda item: (item.score, item.image_url is not None, item.page_url),
        reverse=True,
    )
