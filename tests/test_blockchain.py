"""Unit tests for blockchain pipeline (anchoring and verification)."""

from __future__ import annotations

import unittest
from uuid import uuid4

from blockchain.blockchain_pipeline import verify_on_chain, write_to_blockchain
from config import Settings
from fingerprinting import compute_fingerprint, utc_now_iso


class TestBlockchainPipeline(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings.from_env()
        self.record_id = str(uuid4())
        self.matched_url = "https://example.com/social/post/123"
        self.timestamp = utc_now_iso()
        self.sample_bytes = b"fake_matched_image_content_data"
        self.sha256_hash = compute_fingerprint(
            self.sample_bytes, self.matched_url, self.timestamp
        )

    def test_write_and_verify_record_success(self) -> None:
        res = write_to_blockchain(
            record_id=self.record_id,
            sha256_hash=self.sha256_hash,
            matched_url=self.matched_url,
            settings=self.settings,
        )
        self.assertIn("tx_hash", res)
        self.assertEqual(res.get("status"), "confirmed")

        verification = verify_on_chain(
            record_id=self.record_id,
            expected_hash=self.sha256_hash,
            settings=self.settings,
        )
        self.assertTrue(verification.matches)
        self.assertEqual(verification.record_id, self.record_id)
        self.assertEqual(verification.expected_hash, self.sha256_hash)
        self.assertEqual(verification.on_chain_hash, self.sha256_hash)

    def test_tampered_hash_fails_verification(self) -> None:
        write_to_blockchain(
            record_id=self.record_id,
            sha256_hash=self.sha256_hash,
            matched_url=self.matched_url,
            settings=self.settings,
        )
        tampered_hash = "a" * 64
        verification = verify_on_chain(
            record_id=self.record_id,
            expected_hash=tampered_hash,
            settings=self.settings,
        )
        self.assertFalse(verification.matches)

    def test_non_existent_record_fails_verification(self) -> None:
        random_id = str(uuid4())
        verification = verify_on_chain(
            record_id=random_id,
            expected_hash=self.sha256_hash,
            settings=self.settings,
        )
        self.assertFalse(verification.matches)


if __name__ == "__main__":
    unittest.main()
