import unittest

from blockchain.client import BlockchainError
from blockchain.local import (
    PAYLOAD_PREFIX,
    LocalBlockchainSession,
    decode_payload,
    encode_payload,
)


class LocalBlockchainPayloadTests(unittest.TestCase):
    record_id = "12345678-1234-5678-9abc-def012345678"
    content_hash = "ab" * 32
    source_url = "https://example.com/post/1"

    def test_payload_round_trip(self) -> None:
        payload = encode_payload(self.record_id, self.content_hash, self.source_url)

        self.assertTrue(payload.startswith(PAYLOAD_PREFIX))
        self.assertEqual(
            decode_payload(payload),
            {
                "record_id": self.record_id,
                "content_hash": self.content_hash,
                "source_url": self.source_url,
            },
        )

    def test_payload_is_canonical(self) -> None:
        first = encode_payload(self.record_id, self.content_hash, self.source_url)
        second = encode_payload(self.record_id, self.content_hash, self.source_url)

        self.assertEqual(first, second)

    def test_rejects_unrelated_transaction_data(self) -> None:
        with self.assertRaisesRegex(BlockchainError, "FaceRecord payload"):
            decode_payload(b"unrelated transaction")

    def test_mines_and_reads_back_local_transaction(self) -> None:
        result = LocalBlockchainSession().anchor_and_verify(
            self.record_id, self.content_hash, self.source_url
        )

        self.assertTrue(result.verified)
        self.assertEqual(result.block_number, 1)
        self.assertTrue(result.transaction_hash.startswith("0x"))


if __name__ == "__main__":
    unittest.main()
