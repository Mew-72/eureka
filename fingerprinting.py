"""Canonical SHA-256 fingerprint generation shared with the blockchain phase."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return an immutable, UTC ISO-8601 timestamp used in the fingerprint."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def compute_fingerprint(
    image_bytes: bytes, matched_url: str, fingerprint_timestamp: str
) -> str:
    """Compute SHA-256(image_bytes + URL UTF-8 + timestamp UTF-8), per the PRD."""
    digest = hashlib.sha256()
    digest.update(image_bytes)
    digest.update(matched_url.encode("utf-8"))
    digest.update(fingerprint_timestamp.encode("utf-8"))
    return digest.hexdigest()
