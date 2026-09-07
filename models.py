"""Shared data models for pipeline stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SearchResult:
    """A normalized result returned by any search provider."""

    source: str
    page_url: str
    image_url: str | None
    match_type: str
    score: float
    title: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ContentEvidence:
    """Best-effort content downloaded from a selected search result."""

    page_title: str | None = None
    caption: str | None = None
    platform: str | None = None
    published_at: str | None = None
    image_bytes: bytes | None = None
    image_content_type: str | None = None
