import hashlib
import re
import unittest

from fingerprinting import compute_fingerprint, utc_now_iso


class FingerprintingTests(unittest.TestCase):
    def test_fingerprint_matches_prd_concatenation(self) -> None:
        image = b"image-bytes"
        url = "https://example.com/post/1"
        timestamp = "2026-09-07T10:11:12.123456Z"
        expected = hashlib.sha256(
            image + url.encode() + timestamp.encode()
        ).hexdigest()

        self.assertEqual(compute_fingerprint(image, url, timestamp), expected)

    def test_utc_timestamp_is_canonical(self) -> None:
        self.assertRegex(
            utc_now_iso(),
            re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z"),
        )


if __name__ == "__main__":
    unittest.main()
