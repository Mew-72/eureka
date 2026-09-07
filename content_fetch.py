"""Best-effort retrieval of selected-page metadata and matched image bytes."""

from __future__ import annotations

import io
import ipaddress
import logging
import socket
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from PIL import Image, UnidentifiedImageError

from models import ContentEvidence, SearchResult

LOGGER = logging.getLogger(__name__)
_USER_AGENT = "FaceVerificationHackathon/1.0 (evidence retrieval)"
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 5


class ContentFetcher:
    def __init__(
        self,
        timeout_seconds: float = 15,
        max_download_bytes: int = 15 * 1024 * 1024,
    ):
        self.timeout_seconds = timeout_seconds
        self.max_download_bytes = max_download_bytes
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": _USER_AGENT})

    def fetch(self, result: SearchResult) -> ContentEvidence:
        metadata = self._fetch_page_metadata(result.page_url)
        image_bytes: bytes | None = None
        image_content_type: str | None = None

        if result.image_url:
            try:
                image_bytes, image_content_type = self._fetch_image(result.image_url)
            except (requests.RequestException, ValueError) as exc:
                LOGGER.warning("Matched image download was unavailable: %s", exc)

        return ContentEvidence(
            page_title=metadata.get("page_title") or result.title,
            caption=metadata.get("caption"),
            platform=metadata.get("platform") or self._platform(result.page_url),
            published_at=metadata.get("published_at"),
            image_bytes=image_bytes,
            image_content_type=image_content_type,
        )

    def _fetch_page_metadata(self, page_url: str) -> dict[str, str | None]:
        empty: dict[str, str | None] = {
            "page_title": None,
            "caption": None,
            "platform": None,
            "published_at": None,
        }
        try:
            with self._safe_get(page_url) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if "html" not in content_type:
                    return empty
                content = self._read_limited(response, "page")
        except (requests.RequestException, ValueError) as exc:
            LOGGER.warning("Page metadata was unavailable: %s", exc)
            return empty

        soup = BeautifulSoup(content, "html.parser")

        def meta(*keys: tuple[str, str]) -> str | None:
            for attribute, value in keys:
                element = soup.find("meta", attrs={attribute: value})
                if element and element.get("content"):
                    return str(element["content"]).strip()
            return None

        title = meta(("property", "og:title"), ("name", "twitter:title"))
        if not title and soup.title and soup.title.string:
            title = soup.title.string.strip()

        return {
            "page_title": title,
            "caption": meta(
                ("property", "og:description"), ("name", "description")
            ),
            "platform": meta(("property", "og:site_name"),),
            "published_at": meta(
                ("property", "article:published_time"),
                ("name", "date"),
                ("itemprop", "datePublished"),
            ),
        }

    def _fetch_image(self, image_url: str) -> tuple[bytes, str]:
        with self._safe_get(image_url) as response:
            response.raise_for_status()
            image_bytes = self._read_limited(response, "matched image")
            if not image_bytes:
                raise ValueError("matched image response was empty")
            try:
                with Image.open(io.BytesIO(image_bytes)) as image:
                    image.verify()
                    detected_type = Image.MIME.get(image.format or "", "image/jpeg")
            except (
                Image.DecompressionBombError,
                UnidentifiedImageError,
                OSError,
            ) as exc:
                raise ValueError("matched image response was not a safe valid image") from exc

            content_type = response.headers.get("Content-Type", detected_type)
            return image_bytes, content_type.split(";", 1)[0].strip()

    def _safe_get(self, url: str) -> requests.Response:
        """GET a public HTTP(S) URL while validating every redirect destination."""
        current_url = url
        for _ in range(_MAX_REDIRECTS + 1):
            self._validate_public_url(current_url)
            response = self.session.get(
                current_url,
                timeout=self.timeout_seconds,
                stream=True,
                allow_redirects=False,
            )
            if response.status_code not in _REDIRECT_STATUSES:
                return response

            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("redirect response did not provide a destination")
            current_url = urljoin(current_url, location)

        raise ValueError(f"response exceeded {_MAX_REDIRECTS} redirects")

    def _read_limited(self, response: requests.Response, label: str) -> bytes:
        try:
            declared_size = int(response.headers.get("Content-Length", "0") or 0)
        except ValueError as exc:
            raise ValueError(f"{label} returned an invalid Content-Length") from exc
        if declared_size > self.max_download_bytes:
            raise ValueError(f"{label} exceeded download limit")

        chunks: list[bytes] = []
        downloaded = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            downloaded += len(chunk)
            if downloaded > self.max_download_bytes:
                raise ValueError(f"{label} exceeded download limit")
            chunks.append(chunk)
        return b"".join(chunks)

    @staticmethod
    def _validate_public_url(url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme.lower() not in {"http", "https"}:
            raise ValueError("content URL must use HTTP or HTTPS")
        if not parts.hostname or parts.username or parts.password:
            raise ValueError("content URL has an invalid authority")

        try:
            port = parts.port or (443 if parts.scheme.lower() == "https" else 80)
        except ValueError as exc:
            raise ValueError("content URL has an invalid port") from exc
        if port not in {80, 443}:
            raise ValueError("content URL must use port 80 or 443")

        try:
            addresses = socket.getaddrinfo(
                parts.hostname, port, type=socket.SOCK_STREAM
            )
        except OSError as exc:
            raise ValueError("content URL hostname could not be resolved") from exc
        if not addresses:
            raise ValueError("content URL hostname resolved to no addresses")

        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise ValueError("content URL resolves to a non-public address")

    @staticmethod
    def _platform(url: str) -> str | None:
        hostname = urlsplit(url).hostname
        return hostname.lower().removeprefix("www.") if hostname else None
