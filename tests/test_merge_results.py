import unittest

from models import SearchResult
from search.merge_results import merge_and_rank, normalize_url


def result(source: str, url: str, score: float, image: str | None = None) -> SearchResult:
    return SearchResult(source, url, image, "page_match", score)


class MergeResultsTests(unittest.TestCase):
    def test_normalize_url_removes_fragment_and_tracking_parameters(self) -> None:
        normalized = normalize_url(
            "HTTPS://Example.COM/post/?utm_source=test&b=2&a=1#section"
        )
        self.assertEqual(normalized, "https://example.com/post/?a=1&b=2")

    def test_merge_deduplicates_providers_and_keeps_best_fields(self) -> None:
        google = result(
            "google_vision",
            "https://example.com/post?utm_source=google",
            0.8,
            "https://cdn.example.com/image.jpg",
        )
        pimeyes = result("pimeyes", "https://example.com/post", 0.9)

        merged = merge_and_rank([google], [pimeyes])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].source, "google_vision+pimeyes")
        self.assertEqual(merged[0].score, 0.9)
        self.assertEqual(merged[0].image_url, "https://cdn.example.com/image.jpg")
        self.assertEqual(merged[0].page_url, "https://example.com/post")

    def test_merge_ranks_highest_score_first(self) -> None:
        merged = merge_and_rank(
            [
                result("google_vision", "https://example.com/lower", 0.5),
                result("google_vision", "https://example.com/higher", 0.9),
            ]
        )

        self.assertEqual([item.score for item in merged], [0.9, 0.5])


if __name__ == "__main__":
    unittest.main()
