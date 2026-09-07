import unittest

from search.pimeyes_scraper import parse_result_candidates


class PimEyesResultParsingTests(unittest.TestCase):
    def test_parses_external_pages_and_preserves_display_order(self) -> None:
        results = parse_result_candidates(
            [
                {
                    "page_url": "https://example.com/person?a=1",
                    "image_url": "https://cdn.pimeyes.com/first.jpg",
                    "title": "  First   result  ",
                },
                {
                    "page_url": "https://news.example.org/story",
                    "image_url": "not-a-url",
                    "title": "Second result",
                },
            ]
        )

        self.assertEqual([item.page_url for item in results], [
            "https://example.com/person?a=1",
            "https://news.example.org/story",
        ])
        self.assertEqual(results[0].source, "pimeyes")
        self.assertEqual(results[0].match_type, "face_search_match")
        self.assertEqual(results[0].score, 0.98)
        self.assertEqual(results[0].title, "First result")
        self.assertIsNone(results[1].image_url)

    def test_ignores_pimeyes_session_and_invalid_urls(self) -> None:
        results = parse_result_candidates(
            [
                {"page_url": "https://pimeyes.com/en/results/abc"},
                {"page_url": "https://cdn.pimeyes.com/result.jpg"},
                {"page_url": "javascript:alert(1)"},
                {"page_url": None},
            ]
        )

        self.assertEqual(results, [])

    def test_deduplicates_pages_and_applies_limit(self) -> None:
        results = parse_result_candidates(
            [
                {"page_url": "https://example.com/post?utm_source=pimeyes"},
                {"page_url": "https://example.com/post"},
                {"page_url": "https://example.org/other"},
            ],
            max_results=1,
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].page_url, "https://example.com/post?utm_source=pimeyes")


if __name__ == "__main__":
    unittest.main()
