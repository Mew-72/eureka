"""Best-effort PimEyes browser automation and result normalization."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from models import SearchResult
from search.merge_results import merge_and_rank

LOGGER = logging.getLogger(__name__)
PIMEYES_HOME_URL = "https://pimeyes.com/en"

_CHALLENGE_MARKERS = (
    "verify you are human",
    "too many requests",
    "search limit reached",
    "unusual traffic",
    "access denied",
    "cf-chl-",
)

_RESULT_EXTRACTION_SCRIPT = r"""
const selectors = [
  '#results a[href]',
  '#results [data-href]',
  '#results [data-source-url]',
  '#results [data-page-url]',
  '[data-testid*="result"] a[href]',
  '[class*="result"] a[href]'
];
const nodes = [...new Set(document.querySelectorAll(selectors.join(',')))];
return nodes.map((node) => {
  const rawUrl = node.getAttribute('href')
    || node.getAttribute('data-href')
    || node.getAttribute('data-source-url')
    || node.getAttribute('data-page-url');
  const card = node.closest('article, li, [data-testid*="result"], [class*="result"], [class*="card"]')
    || node.parentElement;
  const image = node.querySelector('img') || (card && card.querySelector('img'));
  let pageUrl = null;
  try { pageUrl = rawUrl ? new URL(rawUrl, document.baseURI).href : null; } catch (_) {}
  return {
    page_url: pageUrl,
    image_url: image ? (image.currentSrc || image.src || null) : null,
    title: (image && image.alt) || node.getAttribute('aria-label') || node.textContent || null
  };
});
"""


def _is_http_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme.lower() in {"http", "https"} and bool(parts.hostname)


def _is_external_page_url(value: str) -> bool:
    if not _is_http_url(value):
        return False
    host = (urlsplit(value).hostname or "").lower().rstrip(".")
    return host != "pimeyes.com" and not host.endswith(".pimeyes.com")


def parse_result_candidates(
    candidates: Sequence[Mapping[str, Any]], max_results: int = 20
) -> list[SearchResult]:
    """Convert browser-extracted candidates into provider-neutral results."""
    if max_results < 1:
        return []

    results: list[SearchResult] = []
    for candidate in candidates:
        raw_page_url = candidate.get("page_url")
        if not isinstance(raw_page_url, str):
            continue
        page_url = raw_page_url.strip()
        if not _is_external_page_url(page_url):
            continue

        raw_image_url = candidate.get("image_url")
        image_url = (
            raw_image_url.strip()
            if isinstance(raw_image_url, str) and _is_http_url(raw_image_url.strip())
            else None
        )
        raw_title = candidate.get("title")
        title = " ".join(raw_title.split()) if isinstance(raw_title, str) else None
        title = title or None
        rank = len(results)
        results.append(
            SearchResult(
                source="pimeyes",
                page_url=page_url,
                image_url=image_url,
                match_type="face_search_match",
                # PimEyes does not expose a stable confidence value. This score
                # preserves its displayed ordering without claiming probability.
                score=max(0.5, round(0.98 - (rank * 0.025), 4)),
                title=title,
            )
        )

    return merge_and_rank(results)[:max_results]


def _click_first(driver: Any, by: Any, selectors: Sequence[tuple[str, str]]) -> bool:
    for strategy, selector in selectors:
        for element in driver.find_elements(getattr(by, strategy), selector):
            try:
                if element.is_displayed() and element.is_enabled():
                    element.click()
                    return True
            except Exception:
                LOGGER.debug(
                    "PimEyes element became unavailable before it could be clicked",
                    exc_info=True,
                )
    return False


def _dismiss_cookie_banner(driver: Any, by: Any) -> None:
    _click_first(
        driver,
        by,
        (
            ("ID", "CybotCookiebotDialogBodyButtonDecline"),
            ("ID", "CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll"),
            ("CSS_SELECTOR", "button[aria-label='Close']"),
        ),
    )


def _upload_image(driver: Any, wait: Any, by: Any, image_path: Path) -> None:
    def file_inputs(current_driver: Any) -> list[Any]:
        return current_driver.find_elements(by.CSS_SELECTOR, "input[type='file']")

    def send_to_first_input(inputs: Sequence[Any]) -> Exception | None:
        last_error: Exception | None = None
        for file_input in inputs:
            try:
                file_input.send_keys(str(image_path))
                return None
            except Exception as exc:  # noqa: BLE001 - try the next file input
                last_error = exc
        return last_error

    inputs = file_inputs(driver)
    first_error = send_to_first_input(inputs) if inputs else None
    if inputs and first_error is None:
        return

    _click_first(
        driver,
        by,
        (
            ("CSS_SELECTOR", "button.upload"),
            ("CSS_SELECTOR", "button[aria-label*='Upload']"),
            (
                "XPATH",
                "//button[contains(., 'Upload') or contains(., 'Start Search')]",
            ),
        ),
    )
    inputs = wait.until(file_inputs)
    last_error = send_to_first_input(inputs)
    if last_error is not None:
        raise RuntimeError("PimEyes file input rejected the probe image") from last_error


def _accept_permissions_and_submit(driver: Any, wait: Any, by: Any) -> None:
    def permission_checkboxes(current_driver: Any) -> list[Any]:
        selectors = (
            ".permissions input[type='checkbox']",
            "[role='dialog'] input[type='checkbox']",
            ".modal input[type='checkbox']",
        )
        for selector in selectors:
            found = current_driver.find_elements(by.CSS_SELECTOR, selector)
            if found:
                return found
        return []

    try:
        checkboxes = wait.until(permission_checkboxes)
    except Exception:  # noqa: BLE001 - permissions are absent on some flows
        checkboxes = []

    for checkbox in checkboxes:
        try:
            if not checkbox.is_selected():
                driver.execute_script("arguments[0].click();", checkbox)
        except Exception as exc:
            raise RuntimeError("Could not accept PimEyes search permissions") from exc

    if checkboxes:
        submitted = _click_first(
            driver,
            by,
            (
                ("CSS_SELECTOR", "[role='dialog'] button[type='submit']"),
                ("CSS_SELECTOR", ".modal button[type='submit']"),
                ("CSS_SELECTOR", ".permissions ~ button"),
                ("XPATH", "//button[contains(., 'Start Search') or contains(., 'Search') or contains(., 'Proceed')]"),
            ),
        )
        if not submitted:
            raise RuntimeError("Could not find the PimEyes search confirmation button")


def _wait_for_results(driver: Any, wait: Any, by: Any, starting_url: str) -> None:
    def search_finished(current_driver: Any) -> bool:
        current_url = current_driver.current_url.lower()
        if current_driver.find_elements(
            by.CSS_SELECTOR, "#results, [data-testid*='result']"
        ):
            return True
        body = current_driver.find_elements(by.TAG_NAME, "body")
        body_text = body[0].text.lower() if body else ""
        if any(marker in body_text for marker in _CHALLENGE_MARKERS):
            return True
        return current_url != starting_url.lower() and (
            "result" in current_url or "search" in current_url
        )

    wait.until(search_finished)


def _challenge_message(driver: Any, by: Any) -> str | None:
    body = driver.find_elements(by.TAG_NAME, "body")
    text = body[0].text.lower() if body else ""
    for marker in _CHALLENGE_MARKERS:
        if marker in text:
            return marker
    return None


def _brief_error(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def search_pimeyes(
    image_path: Path,
    *,
    max_results: int = 20,
    timeout_seconds: float = 30.0,
    headless: bool = True,
    driver_factory: Callable[[Any], Any] | None = None,
) -> list[SearchResult]:
    """Search PimEyes and return real external source pages when exposed.

    All browser, CAPTCHA, rate-limit, and DOM failures are deliberately converted
    to an empty list so the primary Google Vision provider can still complete.
    """
    driver: Any | None = None
    try:
        from selenium import webdriver  # type: ignore[import-not-found]
        from selenium.webdriver.common.by import By  # type: ignore[import-not-found]
        from selenium.webdriver.support.ui import (  # type: ignore[import-not-found]
            WebDriverWait,
        )

        options = webdriver.ChromeOptions()
        options.page_load_strategy = "eager"
        options.add_argument("--window-size=1440,1000")
        options.add_argument("--lang=en-US")
        if headless:
            options.add_argument("--headless=new")

        factory = driver_factory or (
            lambda chrome_options: webdriver.Chrome(options=chrome_options)
        )
        active_driver: Any = factory(options)
        driver = active_driver
        active_driver.set_page_load_timeout(timeout_seconds)
        wait = WebDriverWait(active_driver, timeout_seconds)

        active_driver.get(PIMEYES_HOME_URL)
        starting_url = active_driver.current_url
        _dismiss_cookie_banner(active_driver, By)
        _upload_image(active_driver, wait, By, image_path.expanduser().resolve())
        _accept_permissions_and_submit(active_driver, wait, By)
        _wait_for_results(active_driver, wait, By, starting_url)

        challenge = _challenge_message(active_driver, By)
        if challenge:
            LOGGER.warning("PimEyes search unavailable (%s)", challenge)
            return []

        payload = active_driver.execute_script(_RESULT_EXTRACTION_SCRIPT) or []
        results = parse_result_candidates(payload, max_results=max_results)
        if not results:
            LOGGER.warning(
                "PimEyes returned no exposed external source URLs; results may be "
                "empty, paywalled, or the page structure may have changed"
            )
        return results
    except Exception as exc:  # noqa: BLE001 - provider is intentionally best-effort
        LOGGER.warning("PimEyes search unavailable: %s", _brief_error(exc))
        return []
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                LOGGER.debug("Could not close the PimEyes browser", exc_info=True)
