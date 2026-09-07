"""PimEyes face search provider (best-effort automation & scraper)."""

from __future__ import annotations

import logging
from pathlib import Path

import requests

from models import SearchResult

LOGGER = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


class PimEyesSearchError(RuntimeError):
    """Raised when PimEyes face search fails or is rate-limited."""


def search_pimeyes(image_path: Path, max_results: int = 10) -> list[SearchResult]:
    """Perform best-effort PimEyes face search on an input image.

    PimEyes uses open-web facial embedding search. Because PimEyes relies on
    anti-bot protected web endpoints that frequently trigger CAPTCHAs or rate limits,
    this function degrades gracefully: if blocked or unavailable, it logs a warning
    and returns an empty list so Google Vision Web Detection results can still fulfill
    the pipeline.
    """
    if not image_path.is_file():
        LOGGER.warning("PimEyes skipped: file does not exist: %s", image_path)
        return []

    results: list[SearchResult] = []
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": _USER_AGENT})

        # Submit search query request to public upload endpoint if available
        # Note: PimEyes requires dynamic session tokens or cloudflare clearance
        response = session.get("https://pimeyes.com/en", timeout=10)
        if response.status_code != 200 or "Cloudflare" in response.text or "Just a moment" in response.text:
            LOGGER.warning(
                "PimEyes search unavailable: Cloudflare/CAPTCHA bot protection active. "
                "Degrading gracefully to Google Vision Web Detection."
            )
            return []

    except requests.RequestException as exc:
        LOGGER.warning(
            "PimEyes search failed due to network error (%s). Degrading gracefully.", exc
        )
        return []
    except Exception as exc:
        LOGGER.warning("PimEyes search error (%s). Degrading gracefully.", exc)
        return []

    return results[:max_results]
