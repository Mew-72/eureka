import unittest
from types import SimpleNamespace

from search.vision_search import parse_web_detection


def image(url: str) -> SimpleNamespace:
    return SimpleNamespace(url=url)


class VisionSearchTests(unittest.TestCase):
    def test_parse_web_detection_uses_page_relevance(self) -> None:
        detection = SimpleNamespace(
            pages_with_matching_images=[
                SimpleNamespace(
                    url="https://example.com/full",
                    score=0.4,
                    page_title="Full match",
                    full_matching_images=[image("https://example.com/full.jpg")],
                    partial_matching_images=[],
                ),
                SimpleNamespace(
                    url="https://example.com/partial",
                    score=0.9,
                    page_title="Partial match",
                    full_matching_images=[],
                    partial_matching_images=[
                        image("https://example.com/partial.jpg")
                    ],
                ),
            ]
        )

        results = parse_web_detection(detection)

        self.assertEqual(
            [item.match_type for item in results],
            ["partial_matching_image", "full_matching_image"],
        )
        self.assertEqual(results[0].score, 0.9)
        self.assertEqual(results[0].title, "Partial match")

    def test_parse_web_detection_deduplicates_page_images(self) -> None:
        detection = SimpleNamespace(
            pages_with_matching_images=[
                SimpleNamespace(
                    url="https://example.com/page",
                    full_matching_images=[
                        image("https://example.com/one.jpg"),
                        image("https://example.com/two.jpg"),
                    ],
                    partial_matching_images=[],
                )
            ]
        )

        results = parse_web_detection(detection)

        self.assertEqual(len(results), 1)
        self.assertIn(
            results[0].image_url,
            {"https://example.com/one.jpg", "https://example.com/two.jpg"},
        )


if __name__ == "__main__":
    unittest.main()
