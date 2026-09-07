"""Unit tests for search/pimeyes_scraper.py."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from search.pimeyes_scraper import search_pimeyes


class TestPimEyesScraper(unittest.TestCase):
    def test_missing_image_path_returns_empty_list(self) -> None:
        non_existent = Path("non_existent_image.jpg")
        results = search_pimeyes(non_existent)
        self.assertEqual(results, [])

    @patch("search.pimeyes_scraper.requests.Session")
    def test_cloudflare_protection_returns_empty_list(
        self, mock_session_cls: MagicMock
    ) -> None:
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<html><body>Just a moment... Cloudflare security check</body></html>"
        mock_session.get.return_value = mock_response
        mock_session_cls.return_value = mock_session

        dummy_path = Path(__file__)
        results = search_pimeyes(dummy_path)
        self.assertEqual(results, [])

    @patch("search.pimeyes_scraper.requests.Session")
    def test_network_exception_degrades_gracefully(
        self, mock_session_cls: MagicMock
    ) -> None:
        mock_session = MagicMock()
        mock_session.get.side_effect = Exception("Connection timed out")
        mock_session_cls.return_value = mock_session

        dummy_path = Path(__file__)
        results = search_pimeyes(dummy_path)
        self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
