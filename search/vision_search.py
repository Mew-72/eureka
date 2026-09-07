"""Google Cloud Vision Web Detection search provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from models import SearchResult
from search.merge_results import merge_and_rank


class VisionSearchError(RuntimeError):
    """Raised when Google Vision cannot return a usable response."""


def _image_url(image: Any) -> str | None:
    url = getattr(image, "url", None)
    return str(url) if url else None


def parse_web_detection(web_detection: Any, max_results: int = 20) -> list[SearchResult]:
    """Convert a Vision WebDetection response into normalized page results."""
    candidates: list[SearchResult] = []

    for rank, page in enumerate(
        list(getattr(web_detection, "pages_with_matching_images", []))
    ):
        page_url = getattr(page, "url", None)
        if not page_url:
            continue

        full_matches = list(getattr(page, "full_matching_images", []))
        partial_matches = list(getattr(page, "partial_matching_images", []))
        page_score = float(getattr(page, "score", 0.0) or 0.0)
        if full_matches:
            match_type = "full_matching_image"
            base_score = 1.0
            images = full_matches
        elif partial_matches:
            match_type = "partial_matching_image"
            base_score = 0.85
            images = partial_matches
        else:
            match_type = "page_match"
            base_score = 0.65
            images = [None]

        fallback_score = max(0.0, base_score - (rank * 0.005))
        for image in images:
            image_score = float(getattr(image, "score", 0.0) or 0.0)
            relevance = page_score or image_score or fallback_score
            score = max(0.0, min(1.0, relevance))
            candidates.append(
                SearchResult(
                    source="google_vision",
                    page_url=str(page_url),
                    image_url=_image_url(image) if image is not None else None,
                    match_type=match_type,
                    score=round(score, 4),
                    title=str(getattr(page, "page_title", "") or "") or None,
                )
            )

    return merge_and_rank(candidates)[:max_results]


def search_web(image_path: Path, max_results: int = 20) -> list[SearchResult]:
    """Submit image bytes to Google Vision Web Detection."""
    try:
        from google.cloud import vision
    except ImportError as exc:  # pragma: no cover - installation dependent
        raise VisionSearchError(
            "google-cloud-vision is not installed; install requirements.txt"
        ) from exc

    try:
        image_bytes = image_path.read_bytes()
    except OSError as exc:
        raise VisionSearchError(f"Could not read image: {image_path}") from exc

    try:
        client = vision.ImageAnnotatorClient()
        response = client.web_detection(
            image=vision.Image(content=image_bytes),
            max_results=max_results,
        )
    except Exception as exc:
        raise VisionSearchError(
            "Google Vision request failed; check credentials and API access"
        ) from exc

    error_message = getattr(getattr(response, "error", None), "message", "")
    if error_message:
        raise VisionSearchError(f"Google Vision returned an error: {error_message}")

    results = parse_web_detection(response.web_detection, max_results=max_results)
    if not results:
        raise VisionSearchError("Google Vision returned no matching web pages")
    return results
